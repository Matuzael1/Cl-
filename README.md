# BlackWoves Site

Site em Flask para o clã de PointBlank **BlackWoves**.

## Estrutura

- `app.py` — aplicação principal
- `templates/` — páginas do site
- `static/style.css` — estilos do site
- `requirements.txt` — dependências do projeto
- `gunicorn.conf.py` — configuração do Gunicorn
- `nginx/blackwoves.conf` — configuração do Nginx para produção
- `systemd/blackwoves.service` — serviço do sistema para iniciar em uptime
- `.env.example` — variáveis de ambiente
- `.github/workflows/deploy.yml` — deploy automáticop para GitHub Actions

## Execução local

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# ou no Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Acesse:

```text
http://localhost:5000
```

## Produção com Nginx + HTTPS

### 1) Ajuste as variáveis de ambiente

Copie o arquivo `.env.example` para `.env` e edite os valores reais:

```bash
cp .env.example .env
```

Preencha:

- `SECRET_KEY`
- `EMAIL_FROM`
- `EMAIL_TO`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `APP_DOMAIN=blackwoves.com.br`

### 2) Instale o Gunicorn e dependências

```bash
pip install -r requirements.txt
```

### 3) Configure o serviço do sistema

No servidor Linux, copie o arquivo:

```bash
sudo cp systemd/blackwoves.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable blackwoves
sudo systemctl start blackwoves
```

### 4) Configure o Nginx

```bash
sudo cp nginx/blackwoves.conf /etc/nginx/conf.d/
sudo nginx -t
sudo systemctl reload nginx
```

### 5) HTTPS com Certbot

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d blackwoves.com.br -d www.blackwoves.com.br
```

### 6) DNS

No provedor de domínio, configure:

- `A` → IP do servidor (apontando para o VPS)
- `www` → CNAME para `blackwoves.com.br`

## Deploy com GitHub Actions

1. Crie um repositório no GitHub.
2. Configure as secrets do repositório:
   - `SSH_PRIVATE_KEY`
   - `SERVER_USER`
   - `SERVER_HOST`
   - `APP_DIR`
3. Faça push do projeto.
4. O workflow em `.github/workflows/deploy.yml` faz o deploy automaticamente no VPS.

## Observação

Se o comando `python` não funcionar no Windows, use:

```bash
py app.py
```
