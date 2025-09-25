import hashlib
import secrets
import string
from cryptography.fernet import Fernet


class CryFernet:
    def __init__(self, key: str):
        self.fernet = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self.fernet.decrypt(value.encode()).decode()


def hash(value: str, key: str) -> str:
    sha256 = hashlib.sha256()
    input = value + key if key else ""
    sha256.update(input.encode("utf-8"))
    return sha256.hexdigest()


def generator(size: int = 16, use_special: bool = False):
    """
    to generate a custom alphabet.

    :param size: the string length
    :param use_special:  wether include special characters
    :return: str
    """
    base_alphabet = string.ascii_letters + string.digits
    alphabet = base_alphabet + (string.punctuation if use_special else "")

    def generator():
        return "".join(secrets.choice(alphabet) for _ in range(size))

    return generator
