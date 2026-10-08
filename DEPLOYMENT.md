# Publicação do Blackwolves

O projeto está preparado para GitHub Actions, Gunicorn, Nginx, systemd e HTTPS. A publicação ainda depende de recursos externos que não existem no workspace: repositório/conta GitHub, VPS Ubuntu com IP público, DNS do domínio e credencial SMTP.

## 1. Publicar no GitHub

O repositório local já está inicializado na branch `main`. Revise os arquivos e publique:

```powershell
# Execute estes comandos dentro da pasta BlackWovesSite.
git add -A
git commit -m "Prepare Blackwolves site for production"
git remote add origin https://github.com/Matuzael1/Cl-.git
git push -u origin main
```

O `.gitignore` exclui `.env`, bancos SQLite, `.secrets/`, ambientes virtuais, caches e o JDK que estava em `templates/oracleJdk-27/`. A chave pública de recrutamento (`static/recruitment-public.pem`) é necessária no site; a chave privada de leitura nunca deve ser enviada ao GitHub, ao VPS ou ao workflow.

## 2. Preparar domínio e VPS

Use Ubuntu 22.04 ou 24.04 com SSH e acesso sudo. Crie registros DNS `A` para `blackwolves.com.br` e `www.blackwolves.com.br`, ambos apontando ao IP público do VPS. Libere TCP `22`, `80` e `443` no firewall do provedor antes de instalar o certificado.

Depois que o repositório estiver público no GitHub e o DNS estiver propagado, rode no VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/Matuzael1/Cl-/main/scripts/bootstrap_ubuntu.sh -o /tmp/blackwolves-bootstrap.sh
sudo bash /tmp/blackwolves-bootstrap.sh https://github.com/Matuzael1/Cl-.git
```

O script instala Python, Git, Nginx e Certbot; clona a branch `main`; cria o usuário do serviço e o usuário `deploy`; prepara o ambiente virtual; gera `SECRET_KEY` e `NEWSLETTER_FERNET_KEY`; configura `.env` com permissão `600`; coloca o banco em `/home/blackwolves/data/blackwolves.db`; instala systemd e Nginx; e solicita o certificado HTTPS.

Durante a execução, digite diretamente no terminal SSH a senha do administrador e a senha de app do Gmail. O script não imprime esses valores. Uma chave pública SSH do GitHub Actions pode ser adicionada quando solicitada; pressione Enter para instalá-la depois manualmente. Se o repositório for privado, configure acesso de leitura do VPS ao GitHub antes do clone e do `git pull`.

O Certbot só consegue emitir o certificado quando DNS e firewall estiverem prontos. Se a emissão falhar, corrija DNS/portas e repita a configuração de Certbot no VPS.

## 3. Ativar deploy automático

Crie uma chave Ed25519 dedicada para o GitHub Actions no computador administrador e instale a chave pública no usuário `deploy` do VPS. Cadastre estes secrets em **GitHub > Settings > Secrets and variables > Actions**:

- `SSH_PRIVATE_KEY`: chave privada dedicada, nunca a chave pessoal.
- `SERVER_KNOWN_HOSTS`: fingerprint/linha `known_hosts` do VPS verificada por um canal confiável.
- `SERVER_USER`: `deploy`.
- `SERVER_HOST`: IP público ou hostname SSH do VPS.
- `APP_DIR`: `/home/blackwolves/BlackWolvesSite`.

O workflow executa `pytest` em pull requests e pushes para `main`; somente pushes bem-sucedidos em `main` fazem deploy. Depois do restart, ele verifica o endpoint HTTPS `/healthz`.

## 4. Conferir e manter

Confirme `https://blackwolves.com.br/healthz` retornando `{"status":"ok"}` e confira `sudo systemctl status blackwolves`, `sudo nginx -t` e `sudo certbot renew --dry-run` no VPS.

O recrutamento exige que o administrador mantenha uma cópia segura da chave privada E2EE fora do servidor. Faça backup protegido do banco, do `.env` (incluindo `NEWSLETTER_FERNET_KEY`) e da chave privada E2EE. Sem essas chaves, dados cifrados antigos não podem ser recuperados.

O código e as imagens locais estão prontos, mas este ambiente não tem acesso à conta GitHub, ao provedor DNS, ao VPS nem à senha de app SMTP. Portanto não é possível criar o repositório remoto, alterar DNS, emitir o certificado ou confirmar uma publicação pública a partir daqui.