# Blackwolves Site

Site Flask do clã Blackwolves, com painel administrativo, inscrições cifradas no navegador e lista de novidades por e-mail.

Para publicar pela primeira vez com bootstrap de VPS, DNS, HTTPS e deploy automático, siga [DEPLOYMENT.md](DEPLOYMENT.md). O deploy real depende de criar o repositório GitHub, configurar o DNS, ter um VPS e fornecer a senha SMTP diretamente no servidor.

## Rodar localmente

```powershell
$env:PYTHON = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $env:PYTHON -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Não foi possível criar .venv" }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Antes de iniciar, edite `.env`: use `APP_ENV=development`, escolha uma senha local para `ADMIN_PASSWORD` e gere a chave da lista de e-mails com `py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, colando o resultado em `NEWSLETTER_FERNET_KEY`. Para testar o envio real, configure também as credenciais SMTP.

Antes de abrir o formulário, gere as chaves E2EE no computador que ficará com a chave privada:

```powershell
.\.venv\Scripts\python.exe scripts/generate_recruitment_keys.py
```

O arquivo `static/recruitment-public.pem` é público e deve ser publicado junto com o site. A chave `.secrets/recruitment-private.pem` é privada: não a envie ao GitHub, VPS, e-mail ou chat. Mantenha cópias de segurança offline em local protegido. Configure valores reais no `.env`; este arquivo é ignorado pelo Git.

Depois dessa configuração, inicie o servidor local:

```powershell
.\.venv\Scripts\python.exe app.py
```

Abra `http://127.0.0.1:5000`. Se a porta 5000 já estiver ocupada, use `$env:PORT = '5001'` antes do comando e abra `http://127.0.0.1:5001`.

## Publicação no VPS

São necessários um VPS Ubuntu com acesso sudo, o domínio `blackwolves.com.br`, acesso ao DNS e um repositório GitHub. Esses recursos externos não podem ser criados ou ativados pelo código local.

O caminho recomendado de primeira instalação está em [DEPLOYMENT.md](DEPLOYMENT.md). A seção abaixo mantém o procedimento manual como alternativa.

### 1. Preparar o DNS

No provedor do domínio, crie um registro `A` para `blackwolves.com.br` apontando ao IPv4 do VPS e outro `A` para `www` apontando ao mesmo endereço. Aguarde a propagação antes de solicitar o certificado.

### 2. Preparar o repositório

No GitHub, crie um repositório e publique o projeto na branch `main`. Confirme que `static/recruitment-public.pem` está incluída e que `.secrets/`, `.env` e `blackwolves.db` não estão versionados. Nunca use `--force` para gerar outra chave depois de receber inscrições: inscrições antigas dependem da chave privada original.

### 3. Preparar o VPS

Conecte por SSH e instale os pacotes:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx
sudo adduser --system --group --home /home/blackwolves blackwolves
sudo install -d -o blackwolves -g blackwolves -m 0750 /home/blackwolves/data
sudo -u blackwolves git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git /home/blackwolves/BlackwolvesSite
cd /home/blackwolves/BlackwolvesSite
sudo -u blackwolves python3 -m venv .venv
sudo -u blackwolves .venv/bin/pip install -r requirements.txt
sudo cp systemd/blackwolves.service /etc/systemd/system/blackwolves.service
sudo cp nginx/blackwolves.conf /etc/nginx/sites-available/blackwolves
sudo ln -s /etc/nginx/sites-available/blackwolves /etc/nginx/sites-enabled/blackwolves
```

Configure `/home/blackwolves/BlackwolvesSite/.env` com valores reais e não compartilhe o arquivo. Gere `SECRET_KEY` com `python3 -c 'import secrets; print(secrets.token_hex(32))'`. Defina `APP_ENV=production`, um `ADMIN_USERNAME` e uma senha forte e exclusiva em `ADMIN_PASSWORD`. Para Gmail, ative a verificação em duas etapas e use uma senha de app em `SMTP_PASSWORD`, não a senha normal da conta.

Defina também `DATABASE_PATH=/home/blackwolves/data/blackwolves.db` no `.env`. A pasta de dados fica fora do checkout Git e é a única pasta gravável pelo serviço systemd.

Gere também a chave para cifrar a lista de e-mails e salve o valor em `NEWSLETTER_FERNET_KEY` no `.env`:

```bash
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Mantenha uma cópia segura dessa chave fora do repositório. Ela é necessária para enviar mensagens à lista já cadastrada; perder ou trocar a chave sem migração torna os endereços armazenados ilegíveis.

```bash
sudo chown blackwolves:blackwolves /home/blackwolves/BlackwolvesSite/.env
sudo chmod 600 /home/blackwolves/BlackwolvesSite/.env
sudo systemctl daemon-reload
sudo systemctl enable --now blackwolves
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d blackwolves.com.br -d www.blackwolves.com.br --redirect
```

Confira o site em `https://blackwolves.com.br` e o serviço com `sudo systemctl status blackwolves`. Depois que o Certbot configurar TLS, force HTTPS no Nginx e verifique a renovação com `sudo certbot renew --dry-run`.

### 4. Ativar deploy pelo GitHub Actions

Use o usuário `deploy` criado pelo bootstrap e instale uma chave SSH dedicada. Em **Settings > Secrets and variables > Actions**, cadastre:

- `SSH_PRIVATE_KEY`: chave SSH privada do deploy.
- `SERVER_KNOWN_HOSTS`: linha verificada do `known_hosts` do VPS, obtida por canal confiável.
- `SERVER_USER`: usuário SSH de deploy.
- `SERVER_HOST`: IP ou hostname do VPS.
- `APP_DIR`: `/home/blackwolves/BlackwolvesSite`.

O bootstrap cria regras sudo restritas para o usuário `deploy`: ele só pode atualizar o checkout como `blackwolves`, instalar as dependências definidas pelo repositório e reiniciar o serviço. Faça push em `main`; o workflow executa os testes antes de publicar e verifica `https://blackwolves.com.br/healthz` depois do restart. Não coloque a chave E2EE privada entre os secrets do GitHub Actions.

## Como a proteção funciona

- Login e cadastro são transmitidos por HTTPS em produção; as senhas são armazenadas somente como hashes, nunca como texto reversível. Cookies da sessão usam `HttpOnly`, `SameSite=Lax` e `Secure` em produção.
- O formulário gera uma chave AES-GCM por inscrição no navegador e a protege com a chave RSA pública do site. O servidor armazena apenas o envelope cifrado e envia por e-mail somente um aviso sem dados pessoais.
- Para ler inscrições, abra o painel em HTTPS e selecione a chave privada `.pem` neste navegador. Ela não é enviada ao servidor. Sem a chave privada correspondente, as inscrições não podem ser recuperadas.
- Isso protege os dados armazenados e as notificações contra leitura pelo servidor/banco, mas um site web não pode oferecer a mesma garantia contra código malicioso entregue por um VPS ou domínio comprometido: o JavaScript do formulário é carregado do próprio site. Proteja também a conta do provedor, DNS, GitHub, VPS e dispositivos dos administradores.
- Inscrições antigas que existam em backups anteriores podem continuar legíveis nesses backups. Proteja ou elimine cópias antigas conforme sua política de retenção. Faça backup seguro da chave privada; perdê-la torna as inscrições irrecuperáveis.
- A aba **Novidades** pede consentimento e confirmação do endereço. O painel envia mensagens individualmente aos confirmados e cada mensagem inclui descadastro. Os endereços são cifrados no banco com `NEWSLETTER_FERNET_KEY`; como o servidor precisa enviar as mensagens, essa parte não é E2EE contra o servidor.

## Arquivos de produção

- `gunicorn.conf.py`: servidor WSGI.
- `nginx/blackwolves.conf`: proxy HTTP inicial; Certbot configura HTTPS.
- `systemd/blackwolves.service`: serviço persistente.
- `.github/workflows/deploy.yml`: publicação por push na branch `main`.
