const privateKeyInput = document.querySelector('#private-key-file');

if (privateKeyInput) {
    const status = document.querySelector('#decryption-status');

    function decodeBase64(value) {
        return Uint8Array.from(atob(value), character => character.charCodeAt(0));
    }

    async function decryptApplication(privateKey, encryptedPayload) {
        const envelope = JSON.parse(encryptedPayload);
        const rawKey = await crypto.subtle.decrypt(
            { name: 'RSA-OAEP' },
            privateKey,
            decodeBase64(envelope.wrapped_key),
        );
        const dataKey = await crypto.subtle.importKey(
            'raw',
            rawKey,
            { name: 'AES-GCM' },
            false,
            ['decrypt'],
        );
        const plaintext = await crypto.subtle.decrypt(
            { name: 'AES-GCM', iv: decodeBase64(envelope.iv) },
            dataKey,
            decodeBase64(envelope.ciphertext),
        );
        return JSON.parse(new TextDecoder().decode(plaintext));
    }

    privateKeyInput.addEventListener('change', async () => {
        const file = privateKeyInput.files[0];
        if (!file) return;

        status.textContent = '';
        try {
            if (!window.isSecureContext || !window.crypto?.subtle) {
                throw new Error('A decifragem exige uma conexão HTTPS segura.');
            }

            const pem = await file.text();
            const base64 = pem.replace(/-----[^-]+-----/g, '').replace(/\s/g, '');
            const privateKey = await crypto.subtle.importKey(
                'pkcs8',
                decodeBase64(base64),
                { name: 'RSA-OAEP', hash: 'SHA-256' },
                false,
                ['decrypt'],
            );

            const records = document.querySelectorAll('.application-record[data-encrypted-payload]');
            for (const record of records) {
                const result = await decryptApplication(privateKey, record.dataset.encryptedPayload);
                const output = record.querySelector('pre');
                output.textContent = JSON.stringify(result, null, 2);
                output.hidden = false;
            }
            status.textContent = `${records.length} inscrição(ões) decifrada(s) localmente.`;
        } catch (error) {
            status.textContent = error.message || 'Não foi possível decifrar as inscrições com essa chave.';
        }
    });
}