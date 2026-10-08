# Blackwolves Site

Site Flask do clã Blackwolves, com painel administrativo, recrutamento cifrado no navegador, newsletter e lista de banimentos.

## Rodar localmente

No PowerShell, dentro da pasta do projeto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Edite `.env` para usar `APP_ENV=development`, defina uma senha local em `ADMIN_PASSWORD` e gere uma chave Fernet para `NEWSLETTER_FERNET_KEY`:

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Para habilitar avisos de recrutamento e newsletter, configure a senha de app do Gmail em `SMTP_PASSWORD`. Inicie o servidor:

```powershell
.\.venv\Scripts\python.exe app.py
```

Abra `http://127.0.0.1:5000`. O healthcheck local fica em `http://127.0.0.1:5000/healthz`.

## Chaves de recrutamento

Gere o par de chaves no computador administrador antes de receber inscrições:

```powershell
.\.venv\Scripts\python.exe scripts/generate_recruitment_keys.py
```

Publique `static/recruitment-public.pem`; mantenha `.secrets/recruitment-private.pem` protegida e com backup offline. Não envie a chave privada ao GitHub, ao VPS, por e-mail ou chat. Sem essa chave, os dados cifrados não podem ser recuperados.

O navegador cifra as inscrições antes do envio com AES-GCM e protege a chave com RSA. Isso protege os dados armazenados, mas não é uma garantia idêntica ao WhatsApp: o JavaScript que cifra os dados é servido pelo próprio domínio. Um VPS, DNS ou GitHub comprometido poderia entregar código alterado. A newsletter usa Fernet para cifrar endereços no banco, mas o servidor precisa lê-los para enviar mensagens.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

O GitHub Actions executa os mesmos testes em pull requests e antes de cada deploy para `main`.

## Produção

O guia de primeira publicação, DNS, VPS, HTTPS, secrets do GitHub e deploy automático está em [DEPLOYMENT.md](DEPLOYMENT.md). São necessários uma conta/repositório GitHub, VPS Ubuntu com IP público, acesso ao DNS de `blackwolves.com.br` e credencial SMTP. Esses recursos não podem ser criados a partir deste workspace; o bootstrap configura o restante no servidor.

Em produção, o banco fica em `/home/blackwolves/data/blackwolves.db`, separado do checkout Git. Faça backup seguro do banco, do `.env` (em especial `NEWSLETTER_FERNET_KEY`) e da chave privada de recrutamento.

## Social

Integrantes devem criar uma conta pelo cadastro usando o nick do jogo como username. O owner vincula essa conta a um membro ativo no painel; somente depois a pessoa pode publicar fotos/vídeos e comentar. São aceitos JPG, PNG, WebP, MP4 e WebM de até 25 MB. O feed é público para leitura; o autor ou owner pode remover posts, e o autor ou owner pode apagar comentários. Em produção, os arquivos ficam em `/home/blackwolves/data/social_uploads`, fora do checkout; inclua essa pasta nos backups do servidor.

## Imagens de notícias

As imagens locais de gameplay e e-sports são capturas da página oficial do PointBlank. Cada card de notícias aponta para o anúncio correspondente da Zepetto.