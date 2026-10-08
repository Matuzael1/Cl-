import os

import pytest

from app import ensure_local_dev_defaults


def test_ensure_local_dev_defaults_creates_needed_values():
    original = {key: os.environ.get(key) for key in ['SECRET_KEY', 'ADMIN_USERNAME', 'ADMIN_PASSWORD', 'NEWSLETTER_FERNET_KEY']}
    try:
        for key in ['SECRET_KEY', 'ADMIN_USERNAME', 'ADMIN_PASSWORD', 'NEWSLETTER_FERNET_KEY']:
            os.environ.pop(key, None)
        values = ensure_local_dev_defaults()

        assert values['SECRET_KEY']
        assert len(values['SECRET_KEY']) >= 32
        assert values['ADMIN_USERNAME']
        assert len(values['ADMIN_PASSWORD']) >= 14
        assert values['NEWSLETTER_FERNET_KEY']
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
