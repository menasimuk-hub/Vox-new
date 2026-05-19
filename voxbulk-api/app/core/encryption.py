from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class Encryptor:
    def __init__(self, key: str):
        self._fernet = Fernet(key.encode("utf-8"))

    def encrypt_str(self, value: str) -> str:
        token = self._fernet.encrypt(value.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt_str(self, token: str) -> str:
        try:
            value = self._fernet.decrypt(token.encode("utf-8"))
            return value.decode("utf-8")
        except InvalidToken as e:
            raise ValueError("Invalid encryption token") from e


def get_encryptor() -> Encryptor:
    settings = get_settings()
    try:
        return Encryptor(settings.encryption_key)
    except ValueError as e:
        if str(settings.env).lower() in {"dev", "development", "local"}:
            # Local installs often still have ENCRYPTION_KEY=change-me. Keep provider
            # setup usable in dev while production still requires a real Fernet key.
            return Encryptor("MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
        raise ValueError(
            "Invalid ENCRYPTION_KEY. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from e
