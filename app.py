import os
import smtplib
import sqlite3
from email.message import EmailMessage

from flask import Flask, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'blackwoves-2026-secret')
DATABASE = os.path.join(app.root_path, 'blackwoves.db')
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
EMAIL_FROM = os.getenv('EMAIL_FROM', 'black.wolves.gm@gmail.com')
EMAIL_TO = os.getenv('EMAIL_TO', 'black.wolves.gm@gmail.com')
SMTP_USERNAME = os.getenv('SMTP_USERNAME', EMAIL_FROM)
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')

application = app


def send_recruitment_email(dados):
    if not SMTP_PASSWORD:
        print('SMTP_PASSWORD não configurado. A inscrição foi salva, mas o e-mail não foi enviado.')
        return False

    mensagem = EmailMessage()
    mensagem['Subject'] = f"Nova inscrição para recrutamento - {dados.get('nome', 'Desconhecido')}"
    mensagem['From'] = EMAIL_FROM
    mensagem['To'] = EMAIL_TO

    corpo = (
        'Nova inscrição para recrutamento - BlackWoves\n\n'
        f"Nome: {dados.get('nome', '')}\n"
        f"Nick no jogo: {dados.get('nick', '')}\n"
        f"Idade: {dados.get('idade', '')}\n"
        f"E-mail: {dados.get('email', '')}\n"
        f"Função preferida: {dados.get('funcao', '')}\n"
        f"Discord: {dados.get('discord', '')}\n"
        f"Experiência: {dados.get('experiencia', '')}\n"
        f"Aceitou os termos: {dados.get('aceite', '')}\n"
    )
    mensagem.set_content(corpo)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(mensagem)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        print(f'Erro ao enviar e-mail de recrutamento: {exc}')
        return False


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
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
        """
    )

    admin_user = db.execute('SELECT 1 FROM users WHERE username = ?', ('admin',)).fetchone()
    if admin_user is None:
        db.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            ('admin', 'black.wolves.gm@gmail.com', generate_password_hash('blackwoves123')),
        )

    if db.execute('SELECT COUNT(*) FROM members').fetchone()[0] == 0:
        db.executemany(
            'INSERT INTO members (nome, cargo, funcao, nivel, status) VALUES (?, ?, ?, ?, ?)',
            [
                ('Vex', 'Líder Supremo', 'Estratégia e comando de ofensiva', 'S+', 'ativo'),
                ('Nyra', 'Coordenadora', 'Organização e comunicação interna', 'A+', 'ativo'),
                ('Kane', 'Invasor', 'Pressão agressiva e suporte móvel', 'A', 'ativo'),
                ('Rook', 'Tático', 'Planejamento e cobertura de rota', 'A', 'ativo'),
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
    return render_template('index.html', total_membros=total_membros, total_eventos=total_eventos)


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
            'data': '02 Out 2026',
            'titulo': 'Treino focado em rota e timing',
            'texto': 'A equipe revisou posições, cobertura e entrada em mapas com maior velocidade e organização coletiva.',
            'imagem': 'https://images.unsplash.com/photo-1542751371-adc38448a05e?auto=format&fit=crop&w=900&q=80'
        },
        {
            'data': '09 Out 2026',
            'titulo': 'Competição interna com rodada intensa',
            'texto': 'As partidas foram disputadas com foco em pressão, comunicação e decisões rápidas no meio do confronto.',
            'imagem': 'https://images.unsplash.com/photo-1511512578047-dfb367046420?auto=format&fit=crop&w=900&q=80'
        },
        {
            'data': '16 Out 2026',
            'titulo': 'Reunião estratégica para a próxima fase',
            'texto': 'O grupo avaliou desempenho, ajustou formações e definiu metas para evoluir em conjunto.',
            'imagem': 'https://images.unsplash.com/photo-1526379095098-d400fd0bf935?auto=format&fit=crop&w=900&q=80'
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


@app.route('/recrutamento', methods=['GET', 'POST'])
def recrutamento():
    sucesso = False
    nome = ''

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        nick = request.form.get('nick', '').strip()
        email = request.form.get('email', '').strip()
        idade = request.form.get('idade', '').strip()
        funcao = request.form.get('role', '').strip()
        experiencia = request.form.get('experiencia', '').strip()
        discord = request.form.get('discord', '').strip()
        aceite = request.form.get('aceite', 'não')

        if nome and nick and email:
            db = get_db()
            db.execute(
                'INSERT INTO inscricoes (nome, nick, email, funcao, experiencia, discord) VALUES (?, ?, ?, ?, ?, ?)',
                (nome, nick, email, funcao, experiencia, discord),
            )
            db.commit()

            dados_email = {
                'nome': nome,
                'nick': nick,
                'idade': idade,
                'email': email,
                'funcao': funcao,
                'experiencia': experiencia,
                'discord': discord,
                'aceite': 'sim' if aceite else 'não',
            }
            send_recruitment_email(dados_email)
            sucesso = True

    return render_template('recrutamento.html', sucesso=sucesso, nome=nome)


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    mensagem = None
    tipo = 'info'

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        nome = request.form.get('nome', '').strip()

        if not all([username, email, password, nome]):
            mensagem = 'Preencha todos os campos do cadastro.'
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
                db.execute(
                    'INSERT INTO inscricoes (nome, nick, email, funcao, experiencia, discord) VALUES (?, ?, ?, ?, ?, ?)',
                    (nome, username, email, 'cadastro', 'Cadastro de acesso do site.', ''),
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
        password = request.form.get('password', '').strip()

        db = get_db()
        usuario = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if usuario and check_password_hash(usuario['password_hash'], password):
            session['logged_in'] = True
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
    inscricoes = db.execute('SELECT * FROM inscricoes ORDER BY criado_em DESC').fetchall()
    total_membros = db.execute('SELECT COUNT(*) FROM members').fetchone()[0]
    total_inscricoes = db.execute('SELECT COUNT(*) FROM inscricoes').fetchone()[0]
    ativos = db.execute("SELECT COUNT(*) FROM members WHERE status = 'ativo'").fetchone()[0]

    stats = {
        'membros': total_membros,
        'inscricoes': total_inscricoes,
        'ativos': ativos,
        'ranking': 'Top 5',
    }

    return render_template('painel.html', membros_cla=membros_db, inscricoes=inscricoes, stats=stats)


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


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
