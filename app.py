import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import socket
import sqlite3
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))


def ensure_local_dev_defaults():
    values = {}

    if not os.getenv('SECRET_KEY'):
        values['SECRET_KEY'] = secrets.token_urlsafe(32)
        os.environ['SECRET_KEY'] = values['SECRET_KEY']

    if not os.getenv('ADMIN_USERNAME'):
        values['ADMIN_USERNAME'] = 'blackwolves-admin'
        os.environ['ADMIN_USERNAME'] = values['ADMIN_USERNAME']

    if not os.getenv('ADMIN_PASSWORD'):
        values['ADMIN_PASSWORD'] = 'Blackwolves@Admin2026!'
        os.environ['ADMIN_PASSWORD'] = values['ADMIN_PASSWORD']

    if not os.getenv('NEWSLETTER_FERNET_KEY'):
        values['NEWSLETTER_FERNET_KEY'] = Fernet.generate_key().decode('ascii')
        os.environ['NEWSLETTER_FERNET_KEY'] = values['NEWSLETTER_FERNET_KEY']

    return values


app = Flask(__name__)
if os.getenv('APP_ENV') != 'production':
    ensure_local_dev_defaults()

secret_key = os.getenv('SECRET_KEY')
if os.getenv('APP_ENV') == 'production':
    if not secret_key or len(secret_key) < 32 or secret_key.startswith('gere-'):
        raise RuntimeError('Configure uma SECRET_KEY aleatória com pelo menos 32 caracteres.')
    if len(os.getenv('ADMIN_PASSWORD', '')) < 14 or os.getenv('ADMIN_PASSWORD', '').startswith('defina-'):
        raise RuntimeError('Configure ADMIN_PASSWORD com pelo menos 14 caracteres.')
    if not os.getenv('SMTP_PASSWORD') or os.getenv('SMTP_PASSWORD') == 'senha_de_app_do_gmail':
        raise RuntimeError('Configure SMTP_PASSWORD com a senha de app do Gmail.')
    newsletter_key = os.getenv('NEWSLETTER_FERNET_KEY', '')
    if not newsletter_key or newsletter_key.startswith('gere-'):
        raise RuntimeError('Configure NEWSLETTER_FERNET_KEY para cifrar endereços de e-mail.')
    try:
        Fernet(newsletter_key.encode('ascii'))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError('NEWSLETTER_FERNET_KEY não é uma chave Fernet válida.') from exc
app.config['SECRET_KEY'] = secret_key or os.urandom(32)
app.config['SESSION_COOKIE_SECURE'] = os.getenv('APP_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = 192 * 1024
DATABASE = os.getenv('DATABASE_PATH', os.path.join(app.root_path, 'blackwolves.db'))
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
EMAIL_FROM = os.getenv('EMAIL_FROM', 'black.wolves.gm@gmail.com')
EMAIL_TO = os.getenv('EMAIL_TO', 'black.wolves.gm@gmail.com')
SMTP_USERNAME = os.getenv('SMTP_USERNAME', EMAIL_FROM)
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
NEWSLETTER_FERNET_KEY = os.getenv('NEWSLETTER_FERNET_KEY', '')
APP_DOMAIN = os.getenv('APP_DOMAIN', '127.0.0.1:5000')
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', f"https://{APP_DOMAIN}" if os.getenv('APP_ENV') == 'production' else 'http://127.0.0.1:5000').rstrip('/')

application = app


def get_csrf_token():
    return session.setdefault('_csrf_token', secrets.token_urlsafe(32))


@app.context_processor
def inject_csrf_token():
    return {'csrf_token': get_csrf_token()}


@app.before_request
def protect_form_posts():
    if request.method != 'POST' or (request.endpoint == 'recrutamento' and request.is_json):
        return

    expected = session.get('_csrf_token', '')
    submitted = request.form.get('csrf_token', '')
    if not expected or not hmac.compare_digest(expected, submitted):
        abort(400)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    if os.getenv('APP_ENV') == 'production':
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response


def send_recruitment_notification():
    if not SMTP_PASSWORD:
        print('SMTP_PASSWORD não configurado. A inscrição foi cifrada, mas o aviso não foi enviado.')
        return False

    mensagem = EmailMessage()
    mensagem['Subject'] = 'Nova inscrição cifrada - Blackwolves'
    mensagem['From'] = EMAIL_FROM
    mensagem['To'] = EMAIL_TO
    mensagem.set_content('Uma nova inscrição cifrada está disponível no painel Blackwolves.')

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(mensagem)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        print(f'Erro ao enviar e-mail de recrutamento: {exc}')
        return False


def send_plain_email(recipient, subject, body):
    if not SMTP_PASSWORD:
        return False

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = EMAIL_FROM
    message['To'] = recipient
    message.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        print(f'Erro no envio de e-mail da newsletter: {exc}')
        return False


def newsletter_fernet():
    if not NEWSLETTER_FERNET_KEY:
        raise RuntimeError('Newsletter indisponível: configure NEWSLETTER_FERNET_KEY.')
    return Fernet(NEWSLETTER_FERNET_KEY.encode('ascii'))


def newsletter_email_digest(email):
    key = base64.urlsafe_b64decode(NEWSLETTER_FERNET_KEY.encode('ascii'))
    lookup_key = hashlib.sha256(key + b'blackwolves-newsletter-lookup').digest()
    return hmac.new(lookup_key, email.strip().lower().encode('utf-8'), hashlib.sha256).hexdigest()


def protect_newsletter_contact(email, unsubscribe_token):
    payload = json.dumps({'email': email, 'unsubscribe_token': unsubscribe_token}).encode('utf-8')
    return newsletter_fernet().encrypt(payload).decode('ascii')


def reveal_newsletter_contact(encrypted_contact):
    return json.loads(newsletter_fernet().decrypt(encrypted_contact.encode('ascii')))


def token_digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def encrypt_recruitment_payload(payload):
    with open(os.path.join(app.root_path, 'static', 'recruitment-public.pem'), 'rb') as key_file:
        public_key = serialization.load_pem_public_key(key_file.read())

    data_key = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(12)
    ciphertext = AESGCM(data_key).encrypt(
        iv,
        json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        None,
    )
    wrapped_key = public_key.encrypt(
        data_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return json.dumps({
        'v': 1,
        'wrapped_key': base64.b64encode(wrapped_key).decode('ascii'),
        'iv': base64.b64encode(iv).decode('ascii'),
        'ciphertext': base64.b64encode(ciphertext).decode('ascii'),
    })


def valid_encrypted_payload(payload):
    if not isinstance(payload, dict) or set(payload) != {'v', 'wrapped_key', 'iv', 'ciphertext'} or payload.get('v') != 1:
        return False
    try:
        wrapped_key = base64.b64decode(payload['wrapped_key'], validate=True)
        iv = base64.b64decode(payload['iv'], validate=True)
        ciphertext = base64.b64decode(payload['ciphertext'], validate=True)
    except (KeyError, TypeError, ValueError):
        return False
    return len(wrapped_key) == 384 and len(iv) == 12 and 16 <= len(ciphertext) <= 100_000


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA secure_delete = ON')
        g._database = db
    return db


@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cargo TEXT NOT NULL,
            funcao TEXT NOT NULL,
            nivel TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ativo',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            data TEXT NOT NULL,
            descricao TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS inscricoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            nick TEXT NOT NULL,
            email TEXT NOT NULL,
            funcao TEXT NOT NULL,
            experiencia TEXT,
            discord TEXT,
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS encrypted_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            encrypted_payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS newsletter_subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_hash TEXT UNIQUE NOT NULL,
            encrypted_contact TEXT NOT NULL,
            confirmation_hash TEXT,
            confirmation_expires_at TEXT,
            unsubscribe_hash TEXT NOT NULL,
            confirmed_at TEXT,
            unsubscribed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS banimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nick TEXT UNIQUE NOT NULL,
            motivo TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    legacy_applications = db.execute('SELECT * FROM inscricoes ORDER BY id').fetchall()
    for legacy in legacy_applications:
        payload = {key: legacy[key] for key in legacy.keys() if key not in {'id', 'criado_em'}}
        db.execute(
            'INSERT INTO encrypted_applications (encrypted_payload, created_at) VALUES (?, ?)',
            (encrypt_recruitment_payload(payload), legacy['criado_em']),
        )
    if legacy_applications:
        db.execute('DELETE FROM inscricoes')

    user_columns = {row['name'] for row in db.execute('PRAGMA table_info(users)')}
    if 'role' not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'member'")

    admin_username = os.getenv('ADMIN_USERNAME', '').strip()
    admin_password = os.getenv('ADMIN_PASSWORD', '')
    if admin_username and admin_password:
        admin_email = os.getenv('ADMIN_EMAIL', EMAIL_FROM)
        existing_admins = db.execute(
            'SELECT id FROM users WHERE username = ? OR email = ?',
            (admin_username, admin_email),
        ).fetchall()
        if len(existing_admins) > 1:
            raise RuntimeError('ADMIN_USERNAME e ADMIN_EMAIL pertencem a contas diferentes.')
        admin_values = (admin_username, admin_email, generate_password_hash(admin_password), 'admin')
        if existing_admins:
            db.execute(
                'UPDATE users SET username = ?, email = ?, password_hash = ?, role = ? WHERE id = ?',
                (*admin_values, existing_admins[0]['id']),
            )
        else:
            db.execute(
                'INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)',
                admin_values,
            )

    if db.execute('SELECT COUNT(*) FROM members').fetchone()[0] == 0:
        db.executemany(
            'INSERT INTO members (nome, cargo, funcao, nivel, status) VALUES (?, ?, ?, ?, ?)',
            [
                ('BlackStriker', 'Administrador e proprietário', 'Planejamento de rotas e leitura do mapa para organizar avanços, controlar posições e manter a comunicação durante as partidas.', 'General de Divisão', 'ativo'),
                ('BodyStyle', 'Administrador e proprietário', 'Precisão nos confrontos, controle de mira e atenção à cobertura dos companheiros, sempre com jogo limpo e decisões seguras.', 'General de Divisão', 'ativo'),
                ('Thzinn', 'Administrador e proprietário', 'Adaptação rápida às estratégias adversárias, análise dos rounds e apoio tático para transformar cada partida em evolução coletiva.', 'General de Divisão', 'ativo'),
            ],
        )

    if db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0:
        db.executemany(
            'INSERT INTO events (titulo, data, descricao) VALUES (?, ?, ?)',
            [
                ('Treino tático do fim de semana', '02 Out 2026', 'Sessão focada em rota, timing e comunicação para maximizar a coordenação da equipe.'),
                ('Competição interna em equipe', '09 Out 2026', 'Partidas em formato de ranking para testar novos posicionamentos e táticas de pressão.'),
                ('Reunião de estratégia', '16 Out 2026', 'Análise pós-jogo e ajustes de formação para a próxima sequência competitiva.'),
            ],
        )

    db.commit()


with app.app_context():
    init_db()


@app.route('/')
def home():
    db = get_db()
    total_membros = db.execute('SELECT COUNT(*) FROM members').fetchone()[0]
    total_eventos = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    total_ativos = db.execute("SELECT COUNT(*) FROM members WHERE status = 'ativo'").fetchone()[0]
    return render_template(
        'index.html',
        total_membros=total_membros,
        total_eventos=total_eventos,
        total_ativos=total_ativos,
    )


@app.route('/healthz')
def healthz():
    try:
        get_db().execute('SELECT 1').fetchone()
    except sqlite3.Error:
        return jsonify(status='error'), 503
    return jsonify(status='ok'), 200


@app.route('/membros')
def membros():
    db = get_db()
    membro_lista = db.execute('SELECT * FROM members ORDER BY CASE status WHEN "ativo" THEN 1 ELSE 2 END, nome ASC').fetchall()
    return render_template('membros.html', membros_cla=membro_lista)


@app.route('/eventos')
def eventos():
    db = get_db()
    lista_eventos = db.execute('SELECT * FROM events ORDER BY data DESC').fetchall()
    return render_template('eventos.html', eventos=lista_eventos)


@app.route('/noticias')
def noticias():
    lista_noticias = [
        {
            'data': '30 set 2026',
            'titulo': 'Notas de atualização: 30/09',
            'texto': 'A atualização oficial reúne eventos ativos, conteúdos da loja e novidades da temporada. Consulte os períodos e detalhes no anúncio.',
            'imagem': url_for('static', filename='images/news/pointblank-gameplay.jpg'),
            'alt': 'Captura de gameplay de Point Blank em confronto num mapa urbano.',
            'fonte': 'https://pointblank.zepetto.com/br/news/view?idx=366&page=1',
        },
        {
            'data': '30 set 2026',
            'titulo': 'PBNC 2026: semifinal presencial',
            'texto': 'Quatro equipes avançaram para as semifinais presenciais do Point Blank National Championship, marcadas para 24 de outubro em São Paulo.',
            'imagem': url_for('static', filename='images/news/pointblank-esports-arena.jpg'),
            'alt': 'Arena lotada durante uma competição oficial de Point Blank.',
            'fonte': 'https://pointblank.zepetto.com/br/news/view?idx=365&page=1',
        },
        {
            'data': '17 set 2026',
            'titulo': 'Ranked Match: Temporada 5',
            'texto': 'A temporada competitiva usa o modo e-sports, com partidas decididas em até 16 rounds e pontuação por desempenho individual.',
            'imagem': url_for('static', filename='images/news/pointblank-rank-interface.jpg'),
            'alt': 'Interface de Point Blank com soldado e árvore de títulos da conta.',
            'fonte': 'https://pointblank.zepetto.com/br/news/view?idx=363&page=1',
        },
    ]
    return render_template('noticias.html', noticias=lista_noticias)


@app.route('/galeria')
def galeria():
    imagens = [
        'https://images.unsplash.com/photo-1542751371-adc38448a05e?auto=format&fit=crop&w=900&q=80',
        'https://images.unsplash.com/photo-1511512578047-dfb367046420?auto=format&fit=crop&w=900&q=80',
        'https://images.unsplash.com/photo-1526379095098-d400fd0bf935?auto=format&fit=crop&w=900&q=80',
        'https://images.unsplash.com/photo-1550745165-9bc0b252726f?auto=format&fit=crop&w=900&q=80'
    ]
    return render_template('galeria.html', imagens=imagens)


@app.route('/banimentos')
def banimentos():
    db = get_db()
    lista_banimentos = db.execute(
        'SELECT * FROM banimentos ORDER BY created_at DESC, nick ASC'
    ).fetchall()
    return render_template('banimentos.html', banimentos=lista_banimentos)


@app.route('/recrutamento', methods=['GET', 'POST'])
def recrutamento():
    if request.method == 'POST':
        if not request.is_json:
            return jsonify(error='A inscrição precisa ser cifrada no navegador.'), 415

        payload = request.get_json(silent=True)
        if not valid_encrypted_payload(payload):
            return jsonify(error='O conteúdo cifrado é inválido.'), 400

        db = get_db()
        db.execute(
            'INSERT INTO encrypted_applications (encrypted_payload) VALUES (?)',
            (json.dumps(payload),),
        )
        db.commit()
        send_recruitment_notification()
        return jsonify(success=True), 201

    return render_template('recrutamento.html')


@app.route('/novidades', methods=['GET', 'POST'])
def novidades():
    status = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        consent = request.form.get('consent') == 'on'
        if not consent or len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            status = 'Informe um e-mail válido e confirme que deseja receber novidades.'
        else:
            db = get_db()
            email_hash = newsletter_email_digest(email)
            subscriber = db.execute(
                'SELECT * FROM newsletter_subscribers WHERE email_hash = ?',
                (email_hash,),
            ).fetchone()
            if subscriber and subscriber['confirmed_at'] and not subscriber['unsubscribed_at']:
                status = 'Esse endereço já está inscrito.'
            else:
                confirmation_token = secrets.token_urlsafe(32)
                unsubscribe_token = secrets.token_urlsafe(32)
                expiry = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
                encrypted_contact = protect_newsletter_contact(email, unsubscribe_token)
                if subscriber:
                    db.execute(
                        'UPDATE newsletter_subscribers SET encrypted_contact = ?, confirmation_hash = ?, '
                        'confirmation_expires_at = ?, unsubscribe_hash = ?, confirmed_at = NULL, '
                        'unsubscribed_at = NULL WHERE id = ?',
                        (encrypted_contact, token_digest(confirmation_token), expiry, token_digest(unsubscribe_token), subscriber['id']),
                    )
                else:
                    db.execute(
                        'INSERT INTO newsletter_subscribers '
                        '(email_hash, encrypted_contact, confirmation_hash, confirmation_expires_at, unsubscribe_hash) '
                        'VALUES (?, ?, ?, ?, ?)',
                        (email_hash, encrypted_contact, token_digest(confirmation_token), expiry, token_digest(unsubscribe_token)),
                    )
                db.commit()
                confirm_url = f'{PUBLIC_BASE_URL}{url_for("confirm_newsletter", token=confirmation_token)}'
                status = 'Confira sua caixa de entrada para confirmar a inscrição.'
                if not send_plain_email(
                    email,
                    'Confirme as novidades Blackwolves',
                    f'Para confirmar o recebimento de novidades do clã, acesse:\n{confirm_url}\n\n'
                    'O link expira em 48 horas. Se você não solicitou a inscrição, ignore esta mensagem.',
                ):
                    status = 'Não foi possível enviar a confirmação agora. Tente novamente mais tarde.'

    return render_template('novidades.html', status=status)


@app.route('/novidades/confirmar/<token>', methods=['GET', 'POST'])
def confirm_newsletter(token):
    db = get_db()
    subscriber = db.execute(
        'SELECT id, confirmation_expires_at FROM newsletter_subscribers WHERE confirmation_hash = ?',
        (token_digest(token),),
    ).fetchone()
    if not subscriber or not subscriber['confirmation_expires_at']:
        return render_template('newsletter-result.html', message='Este link de confirmação não é válido.'), 400

    expires_at = datetime.fromisoformat(subscriber['confirmation_expires_at'])
    if expires_at < datetime.now(timezone.utc):
        return render_template('newsletter-result.html', message='Este link expirou. Inscreva-se novamente para receber outro.'), 410

    if request.method == 'GET':
        return render_template('newsletter-confirm.html', token=token)
    if not hmac.compare_digest(request.form.get('confirmation_token', ''), token):
        return render_template('newsletter-result.html', message='Este link de confirmação não é válido.'), 400

    db.execute(
        'UPDATE newsletter_subscribers SET confirmed_at = ?, confirmation_hash = NULL, confirmation_expires_at = NULL '
        'WHERE id = ?',
        (datetime.now(timezone.utc).isoformat(), subscriber['id']),
    )
    db.commit()
    return render_template('newsletter-result.html', message='Inscrição confirmada. Você receberá as novidades do Blackwolves.')


@app.route('/novidades/cancelar/<token>', methods=['GET', 'POST'])
def unsubscribe_newsletter(token):
    db = get_db()
    subscriber = db.execute(
        'SELECT id FROM newsletter_subscribers WHERE unsubscribe_hash = ? AND unsubscribed_at IS NULL',
        (token_digest(token),),
    ).fetchone()
    if not subscriber:
        return render_template('newsletter-result.html', message='Este link de descadastro não é válido.'), 400
    if request.method == 'POST':
        if not hmac.compare_digest(request.form.get('unsubscribe_token', ''), token):
            return render_template('newsletter-result.html', message='Este link de descadastro não é válido.'), 400
        db.execute(
            'UPDATE newsletter_subscribers SET unsubscribed_at = ? WHERE id = ?',
            (datetime.now(timezone.utc).isoformat(), subscriber['id']),
        )
        db.commit()
        return render_template('newsletter-result.html', message='Descadastro concluído. Você não receberá novos e-mails.')
    return render_template('newsletter-unsubscribe.html', token=token)


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    mensagem = None
    tipo = 'info'

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        nome = request.form.get('nome', '').strip()

        if not all([username, email, password, nome]):
            mensagem = 'Preencha todos os campos do cadastro.'
            tipo = 'error'
        elif (
            len(nome) > 120
            or len(username) > 80
            or len(email) > 254
            or len(password) < 12
            or len(password) > 128
            or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)
        ):
            mensagem = 'Use um e-mail válido, uma senha de 12 a 128 caracteres e limites compatíveis nos demais campos.'
            tipo = 'error'
        else:
            db = get_db()
            existe = db.execute('SELECT 1 FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
            if existe:
                mensagem = 'Usuário ou e-mail já cadastrados.'
                tipo = 'error'
            else:
                db.execute(
                    'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                    (username, email, generate_password_hash(password)),
                )
                db.commit()
                mensagem = 'Cadastro realizado com sucesso! Você pode fazer login no painel.'
                tipo = 'success'

    return render_template('cadastro.html', mensagem=mensagem, tipo=tipo)


@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        usuario = None
        if username and len(username) <= 80 and len(password) <= 128:
            usuario = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if usuario and check_password_hash(usuario['password_hash'], password):
            if usuario['role'] != 'admin':
                erro = 'Sua conta não tem acesso ao painel administrativo.'
                return render_template('login.html', erro=erro), 403
            session.clear()
            session['logged_in'] = True
            session['role'] = usuario['role']
            session['username'] = usuario['username']
            return redirect(url_for('painel'))

        erro = 'Credenciais inválidas. Tente novamente.'

    return render_template('login.html', erro=erro)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/painel')
def painel():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    db = get_db()
    membros_db = db.execute('SELECT * FROM members ORDER BY nome ASC').fetchall()
    inscricoes = db.execute('SELECT * FROM encrypted_applications ORDER BY created_at DESC').fetchall()
    banimentos = db.execute('SELECT * FROM banimentos ORDER BY created_at DESC').fetchall()
    total_membros = db.execute('SELECT COUNT(*) FROM members').fetchone()[0]
    total_inscricoes = db.execute('SELECT COUNT(*) FROM encrypted_applications').fetchone()[0]
    ativos = db.execute("SELECT COUNT(*) FROM members WHERE status = 'ativo'").fetchone()[0]
    total_assinantes = db.execute(
        'SELECT COUNT(*) FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL AND unsubscribed_at IS NULL'
    ).fetchone()[0]
    total_banidos = db.execute('SELECT COUNT(*) FROM banimentos').fetchone()[0]

    stats = {
        'membros': total_membros,
        'inscricoes': total_inscricoes,
        'ativos': ativos,
        'ranking': 'Top 5',
        'assinantes': total_assinantes,
        'banidos': total_banidos,
    }

    csrf_token = get_csrf_token()
    return render_template('painel.html', membros_cla=membros_db, inscricoes=inscricoes, banimentos=banimentos, stats=stats, csrf_token=csrf_token)


@app.route('/painel/newsletter/enviar', methods=['POST'])
def painel_newsletter_enviar():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    if not hmac.compare_digest(
        request.form.get('csrf_token', ''),
        session.get('_csrf_token', ''),
    ):
        return 'Solicitação inválida. Recarregue o painel e tente novamente.', 400

    subject = request.form.get('subject', '').strip().replace('\r', ' ').replace('\n', ' ')
    body = request.form.get('message', '').strip()
    if not subject or len(subject) > 120 or not body or len(body) > 8000:
        flash('Preencha um assunto (até 120 caracteres) e uma mensagem (até 8.000 caracteres).', 'error')
        return redirect(url_for('painel'))

    db = get_db()
    subscribers = db.execute(
        'SELECT encrypted_contact FROM newsletter_subscribers '
        'WHERE confirmed_at IS NOT NULL AND unsubscribed_at IS NULL'
    ).fetchall()
    sent = 0
    for subscriber in subscribers:
        try:
            contact = reveal_newsletter_contact(subscriber['encrypted_contact'])
        except (InvalidToken, KeyError, ValueError):
            continue
        unsubscribe_url = f'{PUBLIC_BASE_URL}{url_for("unsubscribe_newsletter", token=contact["unsubscribe_token"])}'
        email_body = f'{body}\n\n---\nPara deixar de receber novidades, acesse: {unsubscribe_url}'
        if send_plain_email(contact['email'], subject, email_body):
            sent += 1

    flash(f'E-mail enviado para {sent} de {len(subscribers)} assinante(s) confirmado(s).', 'success' if sent else 'error')
    return redirect(url_for('painel'))


@app.route('/painel/banir', methods=['POST'])
def painel_banir():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    nick = request.form.get('nick', '').strip()
    motivo = request.form.get('motivo', '').strip()
    if nick and motivo:
        db = get_db()
        db.execute(
            'INSERT INTO banimentos (nick, motivo) VALUES (?, ?) '
            'ON CONFLICT(nick) DO UPDATE SET motivo = excluded.motivo, created_at = CURRENT_TIMESTAMP',
            (nick, motivo),
        )
        db.commit()
        flash(f'Jogador "{nick}" adicionado à lista de banimento.', 'success')
    else:
        flash('Preencha nick e motivo para registrar o banimento.', 'error')

    return redirect(url_for('painel'))


@app.route('/painel/remover-banimento/<int:ban_id>', methods=['POST'])
def painel_remover_banimento(ban_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    db = get_db()
    db.execute('DELETE FROM banimentos WHERE id = ?', (ban_id,))
    db.commit()
    flash('Registro removido da lista de banimento.', 'success')
    return redirect(url_for('painel'))


@app.route('/painel/adicionar', methods=['POST'])
def painel_adicionar():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    nome = request.form.get('nome', '').strip()
    cargo = request.form.get('cargo', '').strip()
    funcao = request.form.get('funcao', '').strip()
    nivel = request.form.get('nivel', '').strip()
    status = request.form.get('status', 'ativo').strip()

    if nome and cargo and funcao and nivel:
        db = get_db()
        db.execute(
            'INSERT INTO members (nome, cargo, funcao, nivel, status) VALUES (?, ?, ?, ?, ?)',
            (nome, cargo, funcao, nivel, status),
        )
        db.commit()

    return redirect(url_for('painel'))


@app.route('/painel/atualizar/<int:member_id>', methods=['POST'])
def painel_atualizar(member_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    nome = request.form.get('nome', '').strip()
    cargo = request.form.get('cargo', '').strip()
    funcao = request.form.get('funcao', '').strip()
    nivel = request.form.get('nivel', '').strip()
    status = request.form.get('status', 'ativo').strip()

    if nome and cargo and funcao and nivel:
        db = get_db()
        db.execute(
            'UPDATE members SET nome = ?, cargo = ?, funcao = ?, nivel = ?, status = ? WHERE id = ?',
            (nome, cargo, funcao, nivel, status, member_id),
        )
        db.commit()

    return redirect(url_for('painel'))


@app.route('/painel/remover/<int:member_id>', methods=['POST'])
def painel_remover(member_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    db = get_db()
    db.execute('DELETE FROM members WHERE id = ?', (member_id,))
    db.commit()
    return redirect(url_for('painel'))


def resolve_ports():
    configured = os.getenv('PORTS') or os.getenv('PORT', '5000,5001,5002,5003,5004,5005')
    values = []
    for chunk in str(configured).replace(' ', '').split(','):
        if not chunk:
            continue
        if '-' in chunk:
            start, end = chunk.split('-', 1)
            try:
                values.extend(range(int(start), int(end) + 1))
            except ValueError:
                continue
        else:
            try:
                values.append(int(chunk))
            except ValueError:
                continue
    return values or [5000, 5001, 5002, 5003, 5004, 5005]


def choose_port(ports):
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    return ports[0]


if __name__ == '__main__':
    selected_port = choose_port(resolve_ports())
    print(f'Usando porta disponível: {selected_port}')
    app.run(debug=False, host='0.0.0.0', port=selected_port)
