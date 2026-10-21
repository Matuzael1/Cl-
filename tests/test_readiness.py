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
    for path in ('/', '/membros', '/eventos', '/noticias', '/social', '/banimentos', '/recrutamento', '/novidades', '/cadastro', '/login', '/solicitacoes-lgpd', '/reembolso'):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers['X-Content-Type-Options'] == 'nosniff'

    assert client.get('/galeria').status_code == 302
    assert client.get('/galeria').headers['Location'].endswith('/social')
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok'}


def test_news_link_to_official_sources_without_unlicensed_copies(client):
    response = client.get('/noticias')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'unsplash.com' not in html
    assert 'class="news-visual"' not in html
    assert html.count('Ver publica\u00e7\u00e3o oficial') == 3
    assert all(source in html for source in ('idx=366', 'idx=365', 'idx=363'))


def test_roster_page_uses_dedicated_grid_for_member_cards(client):
    html = client.get('/membros').get_data(as_text=True)

    assert 'class="roster-grid"' in html
    assert html.count('class="member-card"') == 3


def test_ban_page_summarizes_game_conduct_and_separates_clan_records(client):
    html = client.get('/banimentos').get_data(as_text=True)

    assert 'Condutas proibidas no clã' in html
    assert 'Software e automação' in html
    assert 'Exploração e manipulação' in html
    assert 'Venda, fraude e credenciais' in html
    assert 'Abuso e perturbação' in html
    assert 'denúncias deliberadamente falsas' in html
    assert 'incentivo à quebra destas regras' in html
    assert 'Este código de conduta é interno do Blackwolves' in html
    assert 'não alteram contas ou punições dentro dos jogos' in html
    assert 'Supercell' not in html
    assert 'Zepetto' not in html


def test_blackwolves_logo_is_served_and_used_by_brand_elements(client):
    response = client.get('/')
    html = response.get_data(as_text=True)
    logo = client.get('/static/images/blackwolves-gaming-logo.jpg')

    assert logo.status_code == 200
    assert logo.mimetype == 'image/jpeg'
    assert logo.data.startswith(b'\xff\xd8\xff')
    assert html.count('/static/images/blackwolves-gaming-logo.jpg') >= 2
    assert 'alt="Blackwolves Gaming"' in html


def test_home_and_recruitment_present_both_clan_games(client):
    home = client.get('/').get_data(as_text=True)
    recruitment = client.get('/recrutamento').get_data(as_text=True)
    encryption_script = client.get('/static/recruitment-e2ee.js').get_data(as_text=True)

    for game in ('PointBlank', 'Clash of Clans'):
        assert game in home
        assert game in recruitment
    assert 'JOGAMOS JUNTOS' in home
    assert 'DOIS JOGOS' not in home
    assert home.index('id="sobre"') < home.index('CLÃ MULTIJOGOS')
    assert 'class="activity-grid"' in home
    assert home.count('class="event-card event-card-featured"') == 4
    assert 'Ambos' in recruitment
    assert "form.querySelector('#game').value" in encryption_script


def test_legal_pages_and_cookie_notice_are_available(client):
    pages = {
        '/privacidade': ('Política de Privacidade', 'Social', 'AES-GCM'),
        '/politica-de-privacidade': ('Política de Privacidade',),
        '/termos': ('Termos de Serviço', 'publicar'),
        '/termos-de-servico': ('Termos de Serviço',),
        '/cookies': ('Aviso de Cookies', 'sessionStorage'),
        '/solicitacoes-lgpd': ('Exercer direitos LGPD', 'E-mail para retorno'),
        '/reembolso': ('Política de Reembolso', 'não recebe pagamentos'),
    }
    for path, expected_content in pages.items():
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200, path
        assert all(content in html for content in expected_content), path
        assert 'cookie-notice' in html
        assert 'Privacidade' in html and 'Termos' in html and 'Cookies' in html

    for path in ('/', '/social', '/login', '/novidades', '/recrutamento'):
        response = client.get(path)
        assert response.status_code == 200
        assert b'cookie-notice' in response.data, path

    script = client.get('/static/cookie-notice.js')
    assert script.status_code == 200
    assert b'sessionStorage' in script.data


def test_public_pages_support_keyboard_and_avoid_third_party_tracking(client):
    paths = (
        '/', '/privacidade', '/termos', '/cookies', '/solicitacoes-lgpd',
        '/reembolso', '/cadastro', '/login', '/recrutamento', '/social',
        '/noticias', '/novidades',
    )
    for path in paths:
        html = client.get(path).get_data(as_text=True)
        assert 'Pular para o conteúdo' in html, path
        assert 'id="main-content"' in html, path
        assert 'fonts.googleapis.com' not in html, path
        assert 'googletagmanager.com' not in html, path
        assert 'google-analytics.com' not in html, path
        assert 'facebook.net' not in html, path

    stylesheet = client.get('/static/style.css').get_data(as_text=True)
    assert ':focus-visible' in stylesheet
    assert 'prefers-reduced-motion' in stylesheet


def test_form_posts_require_csrf_but_recruitment_json_remains_available(client):
    for path in ('/login', '/cadastro', '/novidades', '/solicitacoes-lgpd', '/painel/banir', '/logout'):
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
        'username': 'player-test',
        'email': 'player@example.com',
        'password': 'senha-curta',
        'consent': 'on',
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


def test_privacy_request_is_emailed_without_database_storage(client, monkeypatch):
    sent = []
    monkeypatch.setattr(application, 'send_plain_email', lambda recipient, subject, body: sent.append((recipient, subject, body)) or True)
    client.get('/solicitacoes-lgpd')
    with client.session_transaction() as state:
        csrf_token = state['_csrf_token']

    response = client.post('/solicitacoes-lgpd', data={
        'csrf_token': csrf_token,
        'request_type': 'deletion',
        'email': 'player@example.com',
        'username': 'player-test',
        'details': 'Remover a conta.',
    })

    assert response.status_code == 200
    assert b'Solicita\xc3\xa7\xc3\xa3o encaminhada' in response.data
    assert len(sent) == 1
    assert sent[0][0] == application.EMAIL_TO
    assert 'player@example.com' in sent[0][2]
    with application.app.app_context():
        tables = {row['name'] for row in application.get_db().execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'privacy_requests' not in tables


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

    rejected_upload = member_client.post('/social/publicar', data={
        'csrf_token': csrf_token,
        'caption': 'Mídia sem autorização confirmada.',
        'media': (BytesIO(b'\xff\xd8\xffrejected-image'), 'rejected.jpg', 'image/jpeg'),
    }, content_type='multipart/form-data')
    assert rejected_upload.status_code == 302
    with application.app.app_context():
        assert application.get_db().execute(
            'SELECT COUNT(*) FROM social_posts WHERE user_id = ?', (user['id'],)
        ).fetchone()[0] == 0

    uploaded = member_client.post('/social/publicar', data={
        'csrf_token': csrf_token,
        'caption': 'Primeira publicação de teste.',
        'rights_confirmed': 'on',
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
    assert 'alt="Primeira publicação de teste."' in feed
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
        'rights_confirmed': 'on',
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
        'rights_confirmed': 'on',
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