import secrets
from cryptography.fernet import Fernet

print("token jwt:" + secrets.token_urlsafe(64))

print("fernet key:" + Fernet.generate_key().decode())