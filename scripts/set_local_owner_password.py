import getpass
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv, set_key
from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

if os.getenv('APP_ENV') == 'production':
    raise SystemExit('Este utilitário é somente para o owner de desenvolvimento local.')

credential_file = ROOT / '.secrets' / 'local-dev.env'
if not credential_file.is_file():
    raise SystemExit('Credenciais locais não encontradas. Inicie o app uma vez primeiro.')

local_values = dotenv_values(credential_file)
username = os.getenv('ADMIN_USERNAME') or local_values.get('ADMIN_USERNAME')
if not username:
    raise SystemExit('ADMIN_USERNAME não está configurado.')

password = getpass.getpass('Nova senha owner (14 a 128 caracteres; entrada oculta): ')
confirmation = getpass.getpass('Confirme a senha (entrada oculta): ')
if password != confirmation:
    raise SystemExit('As senhas não coincidem; nenhuma alteração aplicada.')
if len(password) < 14 or len(password) > 128:
    raise SystemExit('Use uma senha entre 14 e 128 caracteres; nenhuma alteração aplicada.')

database_path = os.getenv('DATABASE_PATH') or str(ROOT / 'blackwolves.db')
connection = sqlite3.connect(database_path)
try:
    cursor = connection.execute(
        "UPDATE users SET password_hash = ?, role = 'owner' WHERE username = ?",
        (generate_password_hash(password), username),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise SystemExit('A conta owner configurada não foi encontrada; nenhuma alteração aplicada.')
    connection.commit()
finally:
    connection.close()

set_key(str(credential_file), 'ADMIN_USERNAME', username, quote_mode='always')
set_key(str(credential_file), 'ADMIN_PASSWORD', password, quote_mode='always')
if os.name != 'nt':
    os.chmod(credential_file, 0o600)

print(f'Senha local do owner {username} atualizada; o valor não foi exibido.')