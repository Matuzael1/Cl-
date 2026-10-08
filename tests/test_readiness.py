import base64
from io import BytesIO
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from werkzeug.security import generate_password_hash

import app as application


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(application, 'DATABASE', str(tmp_path / 'site-test.db'))
    monkeypatch.setattr(application, 'SOCIAL_UPLOAD_DIR', str(tmp_path / 'social_uploads'))
    with application.app.app_context():
        application.init_db()
    return application.app.test_client()


def test_healthcheck_and_public_pages(client):
    for path in ('/', '/membros', '/eventos', '/noticias', '/social', '/banimentos', '/recrutamento', '/novidades', '/cadastro', '/login'):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers['X-Content-Type-Options'] == 'nosniff'

    assert client.get('/galeria').status_code == 302
    assert client.get('/galeria').headers['Location'].endswith('/social')
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


def test_social_owner_links_member_and_member_posts_comments_and_media(client):
    with application.app.app_context():
        db = application.get_db()
        member = db.execute(
            "SELECT id FROM members WHERE status = 'ativo' ORDER BY id LIMIT 1"
        ).fetchone()
        db.execute(
            'INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)',
            ('BlackStriker', 'blackstriker@example.com', generate_password_hash('social-member-password'), 'member'),
        )
        db.commit()
        user = db.execute('SELECT id FROM users WHERE username = ?', ('BlackStriker',)).fetchone()

    owner = application.app.test_client()
    with owner.session_transaction() as state:
        state['logged_in'] = True
        state['role'] = 'owner'
        state['username'] = application.os.getenv('ADMIN_USERNAME', 'MatuzaelS')
    owner_panel = owner.get('/painel')
    assert owner_panel.status_code == 200
    assert 'Vincular contas dos membros' in owner_panel.get_data(as_text=True)
    assert 'BlackStriker' in owner_panel.get_data(as_text=True)
    with owner.session_transaction() as state:
        owner_csrf = state['_csrf_token']
    linked = owner.post('/painel/social/vincular', data={
        'csrf_token': owner_csrf,
        'user_id': user['id'],
        'member_id': member['id'],
    })
    assert linked.status_code == 302

    member_client = application.app.test_client()
    member_client.get('/login?next=/social')
    with member_client.session_transaction() as state:
        login_csrf = state['_csrf_token']
    login = member_client.post('/login?next=/social', data={
        'csrf_token': login_csrf,
        'username': 'BlackStriker',
        'password': 'social-member-password',
    })
    assert login.status_code == 302 and login.headers['Location'].endswith('/social')
    page = member_client.get('/social')
    assert page.status_code == 200 and b'Nova publica' in page.data
    with member_client.session_transaction() as state:
        csrf_token = state['_csrf_token']

    uploaded = member_client.post('/social/publicar', data={
        'csrf_token': csrf_token,
        'caption': 'Primeira publicação de teste.',
        'media': (BytesIO(b'\xff\xd8\xfffake-jpeg-data'), 'screenshot.jpg', 'image/jpeg'),
    }, content_type='multipart/form-data')
    assert uploaded.status_code == 302
    with application.app.app_context():
        post = application.get_db().execute(
            'SELECT id, media_filename FROM social_posts WHERE user_id = ?',
            (user['id'],),
        ).fetchone()
    assert post is not None
    assert member_client.get(f'/social-media/{post["media_filename"]}').status_code == 200

    comment = member_client.post(f'/social/{post["id"]}/comentar', data={
        'csrf_token': csrf_token,
        'body': 'Ótima partida!',
    })
    assert comment.status_code == 302
    feed = member_client.get('/social').get_data(as_text=True)
    assert 'Primeira publicação de teste.' in feed
    assert 'Ótima partida!' in feed

    public_client = application.app.test_client()
    public_feed = public_client.get('/social')
    assert public_feed.status_code == 200
    assert 'Primeira publicação de teste.' in public_feed.get_data(as_text=True)
    assert 'Ótima partida!' in public_feed.get_data(as_text=True)
    assert public_client.get(f'/social-media/{post["media_filename"]}').status_code == 200


def test_social_unlinked_user_cannot_publish_and_member_cannot_remove_others_post(client):
    with application.app.app_context():
        db = application.get_db()
        members = db.execute(
            "SELECT id, nome FROM members WHERE status = 'ativo' ORDER BY id LIMIT 2"
        ).fetchall()
        db.executemany(
            'INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)',
            [
                ('Social One', 'social-one@example.com', generate_password_hash('social-one-password'), 'member'),
                ('Social Two', 'social-two@example.com', generate_password_hash('social-two-password'), 'member'),
            ],
        )
        db.commit()
        users = db.execute(
            'SELECT id, username FROM users WHERE username IN (?, ?)',
            ('Social One', 'Social Two'),
        ).fetchall()

    unlinked = application.app.test_client()
    unlinked.get('/login')
    with unlinked.session_transaction() as state:
        csrf = state['_csrf_token']
    response = unlinked.post('/login', data={
        'csrf_token': csrf,
        'username': 'Social One',
        'password': 'social-one-password',
    })
    assert response.status_code == 403

    owner = application.app.test_client()
    with owner.session_transaction() as state:
        state['logged_in'] = True
        state['role'] = 'owner'
        state['username'] = os.environ.get('ADMIN_USERNAME', 'MatuzaelS')
    owner.get('/painel')
    with owner.session_transaction() as state:
        owner_csrf = state['_csrf_token']
    for user, member in zip(users, members):
        assert owner.post('/painel/social/vincular', data={
            'csrf_token': owner_csrf,
            'user_id': user['id'],
            'member_id': member['id'],
        }).status_code == 302

    owner_social = owner.get('/social')
    assert owner_social.status_code == 200
    owner_media = owner.post('/social/publicar', data={
        'csrf_token': owner_csrf,
        'caption': 'Post do owner.',
        'media': (BytesIO(b'\xff\xd8\xffowner-image'), 'owner.jpg', 'image/jpeg'),
    }, content_type='multipart/form-data')
    assert owner_media.status_code == 302
    with application.app.app_context():
        post = application.get_db().execute(
            'SELECT id FROM social_posts ORDER BY id DESC LIMIT 1'
        ).fetchone()

    member_client = application.app.test_client()
    member_client.get('/login')
    with member_client.session_transaction() as state:
        csrf = state['_csrf_token']
    login = member_client.post('/login', data={
        'csrf_token': csrf,
        'username': 'Social One',
        'password': 'social-one-password',
    })
    assert login.status_code == 302
    assert member_client.get(login.headers['Location']).status_code == 200
    with member_client.session_transaction() as state:
        member_csrf = state['_csrf_token']
    assert member_client.post(
        f'/social/{post["id"]}/remover',
        data={'csrf_token': member_csrf},
    ).status_code == 403

    video = member_client.post('/social/publicar', data={
        'csrf_token': member_csrf,
        'caption': 'Vídeo da partida.',
        'media': (BytesIO(b'\x1a\x45\xdf\xa3webm-test-data'), 'round.webm', 'video/webm'),
    }, content_type='multipart/form-data')
    assert video.status_code == 302
    with application.app.app_context():
        video_post = application.get_db().execute(
            "SELECT id, media_filename FROM social_posts WHERE media_kind = 'video' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert video_post is not None
    assert member_client.get(f'/social-media/{video_post["media_filename"]}').status_code == 200

    added_comment = member_client.post(f'/social/{post["id"]}/comentar', data={
        'csrf_token': member_csrf,
        'body': 'Comentário do primeiro membro.',
    })
    assert added_comment.status_code == 302
    with application.app.app_context():
        comment = application.get_db().execute(
            'SELECT id FROM social_comments WHERE post_id = ? ORDER BY id DESC LIMIT 1',
            (post['id'],),
        ).fetchone()

    other_member = application.app.test_client()
    other_member.get('/login')
    with other_member.session_transaction() as state:
        other_login_csrf = state['_csrf_token']
    other_login = other_member.post('/login', data={
        'csrf_token': other_login_csrf,
        'username': 'Social Two',
        'password': 'social-two-password',
    })
    assert other_login.status_code == 302
    assert other_member.get(other_login.headers['Location']).status_code == 200
    with other_member.session_transaction() as state:
        other_csrf = state['_csrf_token']
    assert other_member.post(
        f'/social/comentarios/{comment["id"]}/remover',
        data={'csrf_token': other_csrf},
    ).status_code == 403