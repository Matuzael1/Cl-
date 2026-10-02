# BlackWoves Site

Site Flask do clã BlackWoves, com painel administrativo, inscrições cifradas no navegador e lista de novidades por e-mail.

## Rodar localmente

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Antes de iniciar, edite `.env`: use `APP_ENV=development`, escolha uma senha local para `ADMIN_PASSWORD` e gere a chave da lista de e-mails com `py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, colando o resultado em `NEWSLETTER_FERNET_KEY`. Para testar o envio real, configure também as credenciais SMTP.

Antes de abrir o formulário, gere as chaves E2EE no computador que ficará com a chave privada:

```powershell
py scripts/generate_recruitment_keys.py
```

O arquivo `static/recruitment-public.pem` é público e deve ser publicado junto com o site. A chave `.secrets/recruitment-private.pem` é privada: não a envie ao GitHub, VPS, e-mail ou chat. Mantenha cópias de segurança offline em local protegido. Configure valores reais no `.env`; este arquivo é ignorado pelo Git.

Depois dessa configuração, inicie o servidor local:

```powershell
py app.py
```

## Publicação no VPS

São necessários um VPS Ubuntu com acesso sudo, o domínio `blackwoves.com.br`, acesso ao DNS e um repositório GitHub. Esses recursos externos não podem ser criados ou ativados pelo código local.

### 1. Preparar o DNS

No provedor do domínio, crie um registro `A` para `blackwoves.com.br` apontando ao IPv4 do VPS e outro `A` para `www` apontando ao mesmo endereço. Aguarde a propagação antes de solicitar o certificado.

### 2. Preparar o repositório

No GitHub, crie um repositório e publique o projeto na branch `main`. Confirme que `static/recruitment-public.pem` está incluída e que `.secrets/`, `.env` e `blackwoves.db` não estão versionados. Nunca use `--force` para gerar outra chave depois de receber inscrições: inscrições antigas dependem da chave privada original.

### 3. Preparar o VPS

Conecte por SSH e instale os pacotes:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx
sudo adduser --system --group --home /home/blackwoves blackwoves
sudo -u blackwoves git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git /home/blackwoves/BlackWovesSite
cd /home/blackwoves/BlackWovesSite
sudo -u blackwoves python3 -m venv .venv
sudo -u blackwoves .venv/bin/pip install -r requirements.txt
sudo cp systemd/blackwoves.service /etc/systemd/system/blackwoves.service
sudo cp nginx/blackwoves.conf /etc/nginx/sites-available/blackwoves
sudo ln -s /etc/nginx/sites-available/blackwoves /etc/nginx/sites-enabled/blackwoves
```

Configure `/home/blackwoves/BlackWovesSite/.env` com valores reais e não compartilhe o arquivo. Gere `SECRET_KEY` com `python3 -c 'import secrets; print(secrets.token_hex(32))'`. Defina `APP_ENV=production`, um `ADMIN_USERNAME` e uma senha forte e exclusiva em `ADMIN_PASSWORD`. Para Gmail, ative a verificação em duas etapas e use uma senha de app em `SMTP_PASSWORD`, não a senha normal da conta.

Gere também a chave para cifrar a lista de e-mails e salve o valor em `NEWSLETTER_FERNET_KEY` no `.env`:

```bash
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Mantenha uma cópia segura dessa chave fora do repositório. Ela é necessária para enviar mensagens à lista já cadastrada; perder ou trocar a chave sem migração torna os endereços armazenados ilegíveis.

```bash
sudo chown blackwoves:blackwoves /home/blackwoves/BlackWovesSite/.env
sudo chmod 600 /home/blackwoves/BlackWovesSite/.env
sudo systemctl daemon-reload
sudo systemctl enable --now blackwoves
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d blackwoves.com.br -d www.blackwoves.com.br --redirect
```

Confira o site em `https://blackwoves.com.br` e o serviço com `sudo systemctl status blackwoves`. Depois que o Certbot configurar TLS, force HTTPS no Nginx e verifique a renovação com `sudo certbot renew --dry-run`.

### 4. Ativar deploy pelo GitHub Actions

Crie uma chave SSH dedicada para deploy, instale a chave pública no usuário de deploy do VPS e configure sudo sem senha restrito ao comando de reinício do serviço. Em **Settings > Secrets and variables > Actions**, cadastre:

- `SSH_PRIVATE_KEY`: chave SSH privada do deploy.
- `SERVER_KNOWN_HOSTS`: linha verificada do `known_hosts` do VPS, obtida por canal confiável.
- `SERVER_USER`: usuário SSH de deploy.
- `SERVER_HOST`: IP ou hostname do VPS.
- `APP_DIR`: `/home/blackwoves/BlackWovesSite`.

O usuário de deploy precisa poder executar `systemctl restart blackwoves` por sudo sem senha, atualizar o repositório e gravar em `.venv`. Faça push em `main`; acompanhe **Actions** no GitHub. Configure o remoto do repositório no VPS antes do primeiro deploy. Não coloque a chave E2EE privada entre os secrets do GitHub Actions.

## Como a proteção funciona

- Login e cadastro são transmitidos por HTTPS em produção; as senhas são armazenadas somente como hashes, nunca como texto reversível. Cookies da sessão usam `HttpOnly`, `SameSite=Lax` e `Secure` em produção.
- O formulário gera uma chave AES-GCM por inscrição no navegador e a protege com a chave RSA pública do site. O servidor armazena apenas o envelope cifrado e envia por e-mail somente um aviso sem dados pessoais.
- Para ler inscrições, abra o painel em HTTPS e selecione a chave privada `.pem` neste navegador. Ela não é enviada ao servidor. Sem a chave privada correspondente, as inscrições não podem ser recuperadas.
- Isso protege os dados armazenados e as notificações contra leitura pelo servidor/banco, mas um site web não pode oferecer a mesma garantia contra código malicioso entregue por um VPS ou domínio comprometido: o JavaScript do formulário é carregado do próprio site. Proteja também a conta do provedor, DNS, GitHub, VPS e dispositivos dos administradores.
- Inscrições antigas que existam em backups anteriores podem continuar legíveis nesses backups. Proteja ou elimine cópias antigas conforme sua política de retenção. Faça backup seguro da chave privada; perdê-la torna as inscrições irrecuperáveis.
- A aba **Novidades** pede consentimento e confirmação do endereço. O painel envia mensagens individualmente aos confirmados e cada mensagem inclui descadastro. Os endereços são cifrados no banco com `NEWSLETTER_FERNET_KEY`; como o servidor precisa enviar as mensagens, essa parte não é E2EE contra o servidor.

## Arquivos de produção

- `gunicorn.conf.py`: servidor WSGI.
- `nginx/blackwoves.conf`: proxy HTTP inicial; Certbot configura HTTPS.
- `systemd/blackwoves.service`: serviço persistente.
- `.github/workflows/deploy.yml`: publicação por push na branch `main`.
