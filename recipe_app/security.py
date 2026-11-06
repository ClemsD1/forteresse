import base64
import hashlib
import hmac

from cryptography.fernet import Fernet
from flask import current_app


def normalize_email(email):
    return email.strip().lower()


def _fernet():
    return Fernet(current_app.config["FERNET_KEY"].encode("ascii"))


def encrypt_email(email):
    return _fernet().encrypt(email.encode("utf-8"))


def decrypt_email(encrypted_email):
    return _fernet().decrypt(encrypted_email).decode("utf-8")


def email_fingerprint(email):
    encryption_key = base64.urlsafe_b64decode(current_app.config["FERNET_KEY"].encode("ascii"))
    lookup_key = hashlib.sha256(encryption_key + b"email-lookup-v1").digest()
    return hmac.new(lookup_key, normalize_email(email).encode("utf-8"), hashlib.sha256).hexdigest()


def is_safe_redirect_target(target):
    if not target:
        return False
    from urllib.parse import urljoin, urlsplit

    host = urlsplit(urljoin("https://local.invalid", target)).netloc
    return host == "local.invalid"
