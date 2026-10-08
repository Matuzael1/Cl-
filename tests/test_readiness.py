import base64
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import app as application


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(application, 'DATABASE', str(tmp_path / 'site-test.db'))
    with application.app.app_context():
        application.init_db()
    return application.app.test_client()


def test_healthcheck_and_public_pages(client):
    for path in ('/', '/membros', '/eventos', '/noticias', '/galeria', '/banimentos', '/recrutamento', '/novidades', '/cadastro', '/login'):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers['X-Content-Type-Options'] == 'nosniff'

    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok'}


def test_news_use_local_pointblank_assets(client):
    response = client.get('/noticias')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'unsplash.com' not in html
    assert html.count('class="news-visual"') == 3
    assert html.count('Ver publica\u00e7\u00e3o oficial') == 3
    assert all(source in html for source in ('idx=366', 'idx=365', 'idx=363'))

    for image in (
        'pointblank-gameplay.jpg',
        'pointblank-esports-arena.jpg',
        'pointblank-rank-interface.jpg',
    ):
        asset = client.get(f'/static/images/news/{image}')
        assert asset.status_code == 200, image
        assert asset.mimetype == 'image/jpeg', image


def test_form_posts_require_csrf_but_recruitment_json_remains_available(client):
    for path in ('/login', '/cadastro', '/novidades', '/painel/banir', '/logout'):
        assert client.post(path, data={}).status_code == 400, path
    assert client.get('/logout').status_code == 405

    response = client.post('/recrutamento', json={})
    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()['error']


def test_recruitment_accepts_valid_encrypted_payload(client):
    public_key_path = Path(application.app.root_path) / 'static' / 'recruitment-public.pem'
    public_key = serialization.load_pem_public_key(public_key_path.read_bytes())
    data_key = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(12)
    ciphertext = AESGCM(data_key).encrypt(iv, b'{"nick":"test"}', None)
    wrapped_key = public_key.encrypt(
        data_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    payload = {
        'v': 1,
        'wrapped_key': base64.b64encode(wrapped_key).decode('ascii'),
        'iv': base64.b64encode(iv).decode('ascii'),
        'ciphertext': base64.b64encode(ciphertext).decode('ascii'),
    }

    response = client.post('/recrutamento', json=payload)
    assert response.status_code == 201
    assert response.get_json() == {'success': True}


def test_signup_requires_csrf_and_enforces_password_length(client):
    page = client.get('/cadastro')
    assert page.status_code == 200
    with client.session_transaction() as state:
        csrf_token = state['_csrf_token']

    form_data = {
        'csrf_token': csrf_token,
        'nome': 'Player Test',
        'username': 'player-test',
        'email': 'player@example.com',
        'password': 'senha-curta',
    }
    weak_password = client.post('/cadastro', data=form_data)
    assert weak_password.status_code == 200
    with application.app.app_context():
        assert application.get_db().execute(
            'SELECT 1 FROM users WHERE username = ?', ('player-test',)
        ).fetchone() is None

    form_data['password'] = 'senha-forte-1234'
    registered = client.post('/cadastro', data=form_data)
    assert registered.status_code == 200
    with application.app.app_context():
        user = application.get_db().execute(
            'SELECT role FROM users WHERE username = ?', ('player-test',)
        ).fetchone()
    assert user['role'] == 'member'


def test_legacy_admin_role_cannot_access_owner_panel_or_mutate_data(client):
    client.get('/login')
    with client.session_transaction() as state:
        csrf_token = state['_csrf_token']
        state['logged_in'] = True
        state['role'] = 'admin'

    panel = client.get('/painel')
    assert panel.status_code == 302 and panel.headers['Location'].endswith('/login')
    response = client.post('/painel/banir', data={
        'csrf_token': csrf_token,
        'nick': 'Unauthorized',
        'motivo': 'Unauthorized test',
    })
    assert response.status_code == 302 and response.headers['Location'].endswith('/login')
    with application.app.app_context():
        assert application.get_db().execute(
            'SELECT 1 FROM banimentos WHERE nick = ?', ('Unauthorized',)
        ).fetchone() is None


def test_admin_member_management_forms_update_and_remove_members(client):
    with client.session_transaction() as state:
        state['logged_in'] = True
        state['role'] = 'owner'

    page = client.get('/painel')
    assert page.status_code == 200
    with client.session_transaction() as state:
        csrf_token = state['_csrf_token']

    created = client.post('/painel/adicionar', data={
        'csrf_token': csrf_token,
        'nome': 'Novo Player',
        'cargo': 'Membro',
        'nivel': 'Recruta',
        'funcao': 'Treino tático e trabalho em equipe.',
        'status': 'ativo',
    })
    assert created.status_code == 302
    with application.app.app_context():
        member = application.get_db().execute(
            'SELECT id FROM members WHERE nome = ?', ('Novo Player',)
        ).fetchone()
    assert member is not None

    updated = client.post(f'/painel/atualizar/{member["id"]}', data={
        'csrf_token': csrf_token,
        'nome': 'Novo Player Atualizado',
        'cargo': 'Membro',
        'nivel': 'Soldado',
        'funcao': 'Leitura de mapa e comunicação.',
        'status': 'inativo',
    })
    assert updated.status_code == 302
    with application.app.app_context():
        member = application.get_db().execute(
            'SELECT id, status FROM members WHERE nome = ?', ('Novo Player Atualizado',)
        ).fetchone()
    assert member['status'] == 'inativo'

    removed = client.post(f'/painel/remover/{member["id"]}', data={'csrf_token': csrf_token})
    assert removed.status_code == 302
    with application.app.app_context():
        assert application.get_db().execute(
            'SELECT 1 FROM members WHERE id = ?', (member['id'],)
        ).fetchone() is None


def test_admin_event_management_forms_create_update_and_remove_events(client):
    with client.session_transaction() as state:
        state['logged_in'] = True
        state['role'] = 'owner'

    panel = client.get('/painel')
    assert panel.status_code == 200
    with client.session_transaction() as state:
        csrf_token = state['_csrf_token']

    created = client.post('/painel/eventos/adicionar', data={
        'csrf_token': csrf_token,
        'titulo': 'Treino de teste',
        'data': 'A definir',
        'descricao': 'Treino tático e comunicação.',
    })
    assert created.status_code == 302
    with application.app.app_context():
        event = application.get_db().execute(
            'SELECT id FROM events WHERE titulo = ?', ('Treino de teste',)
        ).fetchone()
    assert event is not None

    updated = client.post(f'/painel/eventos/atualizar/{event["id"]}', data={
        'csrf_token': csrf_token,
        'titulo': 'Treino atualizado',
        'data': '20 out 2026',
        'descricao': 'Treino de mapa e comunicação.',
    })
    assert updated.status_code == 302
    assert 'Treino atualizado' in client.get('/eventos').get_data(as_text=True)

    removed = client.post(
        f'/painel/eventos/remover/{event["id"]}',
        data={'csrf_token': csrf_token},
    )
    assert removed.status_code == 302
    with application.app.app_context():
        assert application.get_db().execute(
            'SELECT 1 FROM events WHERE id = ?', (event['id'],)
        ).fetchone() is None