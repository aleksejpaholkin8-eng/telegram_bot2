import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if ENCRYPTION_KEY:
    try:
        cipher = Fernet(ENCRYPTION_KEY.encode())
        logger.info("Шифрование настроено.")
    except Exception as e:
        logger.error(f"Неверный ENCRYPTION_KEY: {e}")
        cipher = None
else:
    cipher = None
    logger.warning("ENCRYPTION_KEY не задан! BYOK будет недоступен.")


def encrypt_key(plain_key: str) -> str:
    if not cipher:
        raise ValueError("Шифрование недоступно: добавь ENCRYPTION_KEY в Railway Variables")
    return cipher.encrypt(plain_key.encode()).decode()


def decrypt_key(encrypted_key: str) -> str:
    if not cipher:
        raise ValueError("Расшифровка недоступна: добавь ENCRYPTION_KEY в Railway Variables")
    return cipher.decrypt(encrypted_key.encode()).decode()
