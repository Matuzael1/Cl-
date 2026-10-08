from pathlib import Path
import argparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_KEY_PATH = ROOT / 'static' / 'recruitment-public.pem'
PRIVATE_KEY_PATH = ROOT / '.secrets' / 'recruitment-private.pem'


def main():
    parser = argparse.ArgumentParser(description='Gera as chaves E2EE de recrutamento.')
    parser.add_argument('--force', action='store_true', help='Substitui o par de chaves existente.')
    args = parser.parse_args()

    if (PUBLIC_KEY_PATH.exists() or PRIVATE_KEY_PATH.exists()) and not args.force:
        parser.error('Já existe uma chave. Use --force somente para uma rotação planejada.')

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public_key = private_key.public_key()

    PRIVATE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_KEY_PATH.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    PRIVATE_KEY_PATH.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    print(f'Chave pública: {PUBLIC_KEY_PATH}')
    print(f'Chave privada: {PRIVATE_KEY_PATH}')
    print('Mantenha a chave privada fora do servidor e do Git. Faça uma cópia de segurança segura.')


if __name__ == '__main__':
    main()