#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR=/home/blackwolves/BlackWolvesSite
DATA_DIR=/home/blackwolves/data
DOMAIN=blackwolves.com.br
REPO_URL="${1:-}"

if [[ "$EUID" -ne 0 ]]; then
    echo "Execute como root: sudo bash scripts/bootstrap_ubuntu.sh <URL_DO_REPOSITORIO>" >&2
    exit 1
fi

if [[ -z "$REPO_URL" ]]; then
    echo "Informe a URL HTTPS ou SSH do repositório GitHub." >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git nginx certbot python3-certbot-nginx python3 python3-pip python3-venv sudo
systemctl stop blackwolves 2>/dev/null || true

getent group blackwolves >/dev/null || addgroup --system blackwolves
id -u blackwolves >/dev/null 2>&1 || adduser --system --ingroup blackwolves --home /home/blackwolves --shell /usr/sbin/nologin blackwolves
id -u deploy >/dev/null 2>&1 || adduser --disabled-password --gecos "" deploy

install -d -o blackwolves -g blackwolves -m 0711 /home/blackwolves
install -d -o blackwolves -g blackwolves -m 0750 "$DATA_DIR"
if [[ ! -d "$APP_DIR/.git" ]]; then
    git clone --branch main -- "$REPO_URL" "$APP_DIR"
else
    sudo -u blackwolves /usr/bin/git -C "$APP_DIR" pull --ff-only origin main
fi

chown -R blackwolves:blackwolves "$APP_DIR"
sudo -u blackwolves python3 -m venv "$APP_DIR/.venv"
sudo -u blackwolves "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u blackwolves "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$APP_DIR/.env" ]]; then
    read -r -p "E-mail administrativo [black.wolves.gm@gmail.com]: " admin_email
    admin_email="${admin_email:-black.wolves.gm@gmail.com}"
    read -r -p "Nome do administrador [blackwolves-admin]: " admin_username
    admin_username="${admin_username:-blackwolves-admin}"

    while true; do
        read -r -s -p "Senha forte para o painel (mínimo 14 caracteres): " admin_password
        printf '\n'
        read -r -s -p "Confirme a senha do painel: " admin_password_confirm
        printf '\n'
        if [[ "$admin_password" == "$admin_password_confirm" && ${#admin_password} -ge 14 ]]; then
            break
        fi
        echo "As senhas precisam coincidir e ter pelo menos 14 caracteres."
    done

    read -r -s -p "Senha de app do Gmail para SMTP: " smtp_password
    printf '\n'
    smtp_password="${smtp_password// /}"
    if [[ -z "$smtp_password" ]]; then
        echo "A senha SMTP é necessária para ativar recrutamento e newsletter." >&2
        exit 1
    fi

    export SECRET_KEY="$("$APP_DIR/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')"
    export NEWSLETTER_FERNET_KEY="$("$APP_DIR/.venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
    export ADMIN_EMAIL="$admin_email"
    export ADMIN_USERNAME="$admin_username"
    export ADMIN_PASSWORD="$admin_password"
    export SMTP_PASSWORD="$smtp_password"
    export APP_DIR DOMAIN DATA_DIR
    "$APP_DIR/.venv/bin/python" - <<'PY'
import os
from dotenv import set_key

env_path = os.path.join(os.environ['APP_DIR'], '.env')
values = {
    'APP_ENV': 'production',
    'SECRET_KEY': os.environ['SECRET_KEY'],
    'ADMIN_USERNAME': os.environ['ADMIN_USERNAME'],
    'ADMIN_PASSWORD': os.environ['ADMIN_PASSWORD'],
    'ADMIN_EMAIL': os.environ['ADMIN_EMAIL'],
    'SMTP_HOST': 'smtp.gmail.com',
    'SMTP_PORT': '587',
    'EMAIL_FROM': 'black.wolves.gm@gmail.com',
    'EMAIL_TO': 'black.wolves.gm@gmail.com',
    'SMTP_USERNAME': 'black.wolves.gm@gmail.com',
    'SMTP_PASSWORD': os.environ['SMTP_PASSWORD'],
    'APP_DOMAIN': os.environ['DOMAIN'],
    'PUBLIC_BASE_URL': f"https://{os.environ['DOMAIN']}",
    'DATABASE_PATH': os.path.join(os.environ['DATA_DIR'], 'blackwolves.db'),
    'NEWSLETTER_FERNET_KEY': os.environ['NEWSLETTER_FERNET_KEY'],
}
for key, value in values.items():
    set_key(env_path, key, value, quote_mode='always')
PY
    chown blackwolves:blackwolves "$APP_DIR/.env"
    chmod 0600 "$APP_DIR/.env"
elif grep -Eq 'gere-|defina-|senha_de_app_do_gmail' "$APP_DIR/.env"; then
    echo "O arquivo .env contém valores de exemplo. Corrija-o antes de continuar." >&2
    exit 1
fi

"$APP_DIR/.venv/bin/python" - "$APP_DIR/.env" "$APP_DIR" "$DATA_DIR" "$DOMAIN" <<'PY'
import os
import sqlite3
import sys
from dotenv import dotenv_values, set_key

env_path, app_dir, data_dir, domain = sys.argv[1:]
database_path = os.path.join(data_dir, 'blackwolves.db')
current = dotenv_values(env_path)
old_path = current.get('DATABASE_PATH')
if not old_path:
    old_path = os.path.join(app_dir, 'blackwolves.db')
elif not os.path.isabs(old_path):
    old_path = os.path.join(app_dir, old_path)
if old_path and os.path.isfile(old_path) and os.path.abspath(old_path) != os.path.abspath(database_path) and not os.path.exists(database_path):
    with sqlite3.connect(old_path) as source, sqlite3.connect(database_path) as destination:
        source.backup(destination)

for key, value in {
    'APP_ENV': 'production',
    'APP_DOMAIN': domain,
    'PUBLIC_BASE_URL': f'https://{domain}',
    'DATABASE_PATH': database_path,
    'EMAIL_TO': 'black.wolves.gm@gmail.com',
}.items():
    set_key(env_path, key, value, quote_mode='always')

values = dotenv_values(env_path)
required = ('SECRET_KEY', 'ADMIN_PASSWORD', 'SMTP_PASSWORD', 'NEWSLETTER_FERNET_KEY')
missing = [key for key in required if not values.get(key) or values[key].startswith(('gere-', 'defina-', 'senha_de_app_'))]
if missing:
    raise SystemExit('Configure estes valores no .env antes de iniciar: ' + ', '.join(missing))
PY
chown blackwolves:blackwolves "$APP_DIR/.env"
chmod 0600 "$APP_DIR/.env"

read -r -p "Chave pública SSH do GitHub Actions para deploy (Enter para configurar depois): " deploy_public_key
if [[ -n "$deploy_public_key" ]]; then
    case "$deploy_public_key" in
        ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-nistp256\ *) ;;
        *) echo "Formato de chave pública SSH não reconhecido." >&2; exit 1 ;;
    esac
    install -d -o deploy -g deploy -m 0700 /home/deploy/.ssh
    touch /home/deploy/.ssh/authorized_keys
    grep -Fxq "$deploy_public_key" /home/deploy/.ssh/authorized_keys || printf '%s\n' "$deploy_public_key" >> /home/deploy/.ssh/authorized_keys
    chown deploy:deploy /home/deploy/.ssh/authorized_keys
    chmod 0600 /home/deploy/.ssh/authorized_keys
fi

cat > /etc/sudoers.d/blackwolves-deploy <<'SUDOERS'
deploy ALL=(blackwolves) NOPASSWD: /usr/bin/git -C /home/blackwolves/BlackWolvesSite pull --ff-only origin main
deploy ALL=(blackwolves) NOPASSWD: /home/blackwolves/BlackWolvesSite/.venv/bin/pip install -r /home/blackwolves/BlackWolvesSite/requirements.txt
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart blackwolves
SUDOERS
chmod 0440 /etc/sudoers.d/blackwolves-deploy
visudo -cf /etc/sudoers.d/blackwolves-deploy

install -m 0644 "$APP_DIR/systemd/blackwolves.service" /etc/systemd/system/blackwolves.service
install -m 0644 "$APP_DIR/nginx/blackwolves.conf" /etc/nginx/sites-available/blackwolves
ln -sfn /etc/nginx/sites-available/blackwolves /etc/nginx/sites-enabled/blackwolves
systemctl daemon-reload
systemctl enable --now blackwolves
nginx -t
systemctl enable --now nginx
systemctl reload nginx

admin_email="$("$APP_DIR/.venv/bin/python" - "$APP_DIR/.env" <<'PY'
import sys
from dotenv import dotenv_values
print(dotenv_values(sys.argv[1]).get('ADMIN_EMAIL', ''))
PY
)"
certbot --nginx --non-interactive --agree-tos --redirect --email "$admin_email" -d "$DOMAIN" -d "www.$DOMAIN"
curl --fail --retry 5 --retry-delay 3 "https://$DOMAIN/healthz"

echo "Instalação concluída. Configure os secrets SSH do workflow no GitHub para ativar deploy automático."