const form = document.querySelector('#recruitment-form');

if (form) {
    const status = document.querySelector('#recruitment-status');
    const submitButton = form.querySelector('button[type="submit"]');

    function decodeBase64(value) {
        return Uint8Array.from(atob(value), character => character.charCodeAt(0));
    }

    function encodeBase64(value) {
        let binary = '';
        for (const byte of new Uint8Array(value)) {
            binary += String.fromCharCode(byte);
        }
        return btoa(binary);
    }

    async function loadPublicKey() {
        const response = await fetch(form.dataset.publicKey, { cache: 'no-store' });
        if (!response.ok) {
            throw new Error('Não foi possível carregar a chave pública do site.');
        }

        const pem = await response.text();
        const base64 = pem.replace(/-----[^-]+-----/g, '').replace(/\s/g, '');
        return crypto.subtle.importKey(
            'spki',
            decodeBase64(base64),
            { name: 'RSA-OAEP', hash: 'SHA-256' },
            false,
            ['encrypt'],
        );
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!form.reportValidity()) return;

        status.hidden = false;
        status.textContent = '';
        submitButton.disabled = true;

        try {
            if (!window.isSecureContext || !window.crypto?.subtle) {
                throw new Error('A inscrição cifrada exige uma conexão HTTPS segura.');
            }

            const publicKey = await loadPublicKey();
            const dataKey = await crypto.subtle.generateKey(
                { name: 'AES-GCM', length: 256 },
                true,
                ['encrypt'],
            );
            const iv = crypto.getRandomValues(new Uint8Array(12));
            const data = {
                nome: form.querySelector('#nome').value,
                nick: form.querySelector('#nick').value,
                idade: form.querySelector('#idade').value,
                email: form.querySelector('#email').value,
                funcao: form.querySelector('#role').value,
                experiencia: form.querySelector('#experiencia').value,
                discord: form.querySelector('#discord').value,
                aceite: form.querySelector('#aceite').checked,
            };
            const ciphertext = await crypto.subtle.encrypt(
                { name: 'AES-GCM', iv },
                dataKey,
                new TextEncoder().encode(JSON.stringify(data)),
            );
            const rawKey = await crypto.subtle.exportKey('raw', dataKey);
            const wrappedKey = await crypto.subtle.encrypt(
                { name: 'RSA-OAEP' },
                publicKey,
                rawKey,
            );

            const response = await fetch(form.action, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    v: 1,
                    wrapped_key: encodeBase64(wrappedKey),
                    iv: encodeBase64(iv),
                    ciphertext: encodeBase64(ciphertext),
                }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Não foi possível enviar a inscrição.');

            form.reset();
            status.textContent = 'Inscrição cifrada enviada. O clã recebeu um aviso sem seus dados pessoais.';
        } catch (error) {
            status.textContent = error.message || 'Falha ao cifrar a inscrição neste dispositivo.';
        } finally {
            submitButton.disabled = false;
        }
    });
}