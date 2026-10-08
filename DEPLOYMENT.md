# Publicação do Blackwolves

O código foi publicado em [Matuzael1/Cl-](https://github.com/Matuzael1/Cl-) e o workflow passou nos testes. O deploy ainda depende de um VPS Ubuntu, DNS apontado ao VPS, senha de app SMTP e secrets do VPS no GitHub.

## 1. Publicar no GitHub

O repositório existente está configurado como `origin` na branch `main`. Para publicar futuras alterações:

```powershell
# Execute estes comandos dentro da pasta BlackWovesSite.
git add -A
git diff --cached --check
git commit -m "Prepare Blackwolves site for production"
git push origin main
```

O primeiro push do projeto completo já foi feito e o histórico README anterior foi preservado por merge, sem force-push.

O `.gitignore` exclui `.env`, bancos SQLite, `.secrets/`, ambientes virtuais, caches e o JDK que estava em `templates/oracleJdk-27/`. A chave pública de recrutamento (`static/recruitment-public.pem`) é necessária no site; a chave privada de leitura nunca deve ser enviada ao GitHub, ao VPS ou ao workflow.

## 2. Preparar domínio e VPS

Use Ubuntu 22.04 ou 24.04 com SSH e acesso sudo. Crie registros DNS `A` para `blackwolves.com.br` e `www.blackwolves.com.br`, ambos apontando ao IP público do VPS. Libere TCP `22`, `80` e `443` no firewall do provedor antes de instalar o certificado.

Na verificação de 08/10/2026, `blackwolves.com.br` ainda respondia com `404` e cabeçalhos da Cloudflare/Nuvemshop, não do VPS deste projeto. Apontar o DNS para um novo VPS substituirá o site que responde hoje nesse domínio; mantenha os registros de e-mail (`MX`, SPF, DKIM e DMARC) e só altere o `A`/`AAAA` web quando o VPS estiver pronto. Se houver `AAAA` para um IPv6 não configurado, remova-o ou configure-o corretamente.

Os nameservers consultados são `ns1018.hostgator.com.br` e `ns1019.hostgator.com.br`; `www` atualmente aponta para a hospedagem da Nuvemshop. No painel DNS da HostGator, depois de preparar o VPS, substitua os registros web `A` de `@` pelo IPv4 do VPS e troque o `CNAME` de `www` para `blackwolves.com.br` (ou use o mesmo `A` do VPS). Não altere registros `MX`/`TXT` do Gmail.

Depois que o repositório estiver público no GitHub e o DNS estiver propagado, rode no VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/Matuzael1/Cl-/main/scripts/bootstrap_ubuntu.sh -o /tmp/blackwolves-bootstrap.sh
sudo bash /tmp/blackwolves-bootstrap.sh https://github.com/Matuzael1/Cl-.git
```

O script instala Python, Git, Nginx e Certbot; clona a branch `main`; cria o usuário do serviço e o usuário `deploy`; prepara o ambiente virtual; gera `SECRET_KEY` e `NEWSLETTER_FERNET_KEY`; configura `.env` com permissão `600`; coloca o banco em `/home/blackwolves/data/blackwolves.db`; instala systemd e Nginx; e solicita o certificado HTTPS.

Durante a execução, digite diretamente no terminal SSH a senha do proprietário `MatuzaelS` e a senha de app do Gmail. A senha precisa ter pelo menos 14 caracteres; a informada no chat é curta demais para produção e não será instalada no VPS. O script não imprime os valores. Uma chave pública SSH do GitHub Actions pode ser adicionada quando solicitada; pressione Enter para instalá-la depois manualmente. Se o repositório for privado, configure acesso de leitura do VPS ao GitHub antes do clone e do `git pull`.

O Certbot só consegue emitir o certificado quando DNS e firewall estiverem prontos. Se a emissão falhar, corrija DNS/portas e repita a configuração de Certbot no VPS.

## 3. Ativar deploy automático

Crie uma chave Ed25519 dedicada para o GitHub Actions no computador administrador e instale a chave pública no usuário `deploy` do VPS. Cadastre estes secrets em **GitHub > Settings > Secrets and variables > Actions**:

No Windows, gere um par dedicado no PowerShell (a chave privada não tem frase-senha para permitir o uso não interativo; proteja-a como secret):

```powershell
ssh-keygen -t ed25519 -C "blackwolves-github-actions" -f "$HOME/.ssh/blackwolves-actions" -N ""
Get-Content "$HOME/.ssh/blackwolves-actions.pub"
```

Cole somente a chave `.pub` no prompt do bootstrap do VPS. Cadastre o conteúdo de `blackwolves-actions` (sem `.pub`) como `SSH_PRIVATE_KEY`. Para `SERVER_KNOWN_HOSTS`, confirme a impressão digital do VPS por canal confiável; não confie cegamente em uma saída de `ssh-keyscan`.

- `SSH_PRIVATE_KEY`: chave privada dedicada, nunca a chave pessoal.
- `SERVER_KNOWN_HOSTS`: fingerprint/linha `known_hosts` do VPS verificada por um canal confiável.
- `SERVER_USER`: `deploy`.
- `SERVER_HOST`: IP público ou hostname SSH do VPS.
- `APP_DIR`: `/home/blackwolves/BlackWolvesSite`.

O workflow executa `pytest` em pull requests e pushes para `main`; somente pushes bem-sucedidos em `main` fazem deploy. Depois do restart, ele verifica o endpoint HTTPS `/healthz`. No primeiro push publicado, o CI passou, mas o job `deploy` foi ignorado porque os cinco secrets de VPS ainda não estavam configurados.

## 4. Conferir e manter

Confirme `https://blackwolves.com.br/healthz` retornando `{"status":"ok"}` e confira `sudo systemctl status blackwolves`, `sudo nginx -t` e `sudo certbot renew --dry-run` no VPS.

O recrutamento exige que o administrador mantenha uma cópia segura da chave privada E2EE fora do servidor. Faça backup protegido do banco, do `.env` (incluindo `NEWSLETTER_FERNET_KEY`) e da chave privada E2EE. Sem essas chaves, dados cifrados antigos não podem ser recuperados.

O código e as imagens locais estão publicados no GitHub, mas este ambiente não tem acesso administrativo ao provedor DNS, ao VPS nem à senha de app SMTP. Portanto a alteração de DNS, emissão do certificado e primeiro deploy real precisam ser concluídos no VPS conforme este guia.