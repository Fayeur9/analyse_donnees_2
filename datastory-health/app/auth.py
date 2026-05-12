"""Module securite : bcrypt, Fernet et JWT."""

import os
import bcrypt
import jwt
import datetime
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Chargement des secrets depuis .env
JWT_SECRET = os.getenv("JWT_SECRET")
FERNET_KEY = os.getenv("FERNET_KEY").encode()

# Initialisation du chiffreur Fernet
cipher = Fernet(FERNET_KEY)


# ============================================================================
# HACHAGE DE MOT DE PASSE - bcrypt
# ============================================================================

def hash_password(password: str) -> str:
    """Hache un mot de passe avec bcrypt (rounds=12)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verifie un mot de passe en le comparant a son empreinte bcrypt."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ============================================================================
# CHIFFREMENT DE CHAMP - Fernet (chiffrement symetrique)
# ============================================================================

def encrypt_field(value: str) -> str:
    """Chiffre un champ sensible et retourne le token chiffre."""
    return cipher.encrypt(value.encode()).decode()


def decrypt_field(encrypted_value: str) -> str:
    """Dechiffre un champ sensible et retourne la valeur d'origine."""
    return cipher.decrypt(encrypted_value.encode()).decode()


# ============================================================================
# GESTION DES TOKENS JWT
# ============================================================================

def create_token(user_id: int, role: str, expires_minutes: int = 30) -> str:
    """Cree un token JWT signe avec expiration courte."""
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_minutes),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """Verifie et decode un JWT. Retourne None si invalide/expire."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"]  # Explicite : evite l'attaque alg=none
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidSignatureError:
        return None
    except Exception:
        return None


# ============================================================================
# TEST / DEMO
# ============================================================================

if __name__ == "__main__":
    print("Test du module auth...\n")
    
    # Test 1 : hachage du mot de passe
    print("1️⃣  Hachage du mot de passe (bcrypt)")
    pwd = "MySecurePassword123!"
    hashed = hash_password(pwd)
    print(f"   Original : {pwd}")
    print(f"   Hache    : {hashed[:40]}...")
    print(f"   Verifie  : {verify_password(pwd, hashed)}")
    print()
    
    # Test 2 : chiffrement de champ
    print("2️⃣  Chiffrement de champ (Fernet)")
    email = "user@example.com"
    encrypted = encrypt_field(email)
    decrypted = decrypt_field(encrypted)
    print(f"   Original : {email}")
    print(f"   Chiffre  : {encrypted[:40]}...")
    print(f"   Dechiffre: {decrypted}")
    print()
    
    # Test 3 : gestion des tokens JWT
    print("3️⃣  Gestion des tokens JWT")
    token = create_token(user_id=1, role="user", expires_minutes=30)
    print(f"   Token (50 premiers caracteres) : {token[:50]}...")
    payload = verify_token(token)
    print(f"   Charge utile : {payload}")
    print()
    
    print("✅ Toutes les fonctions auth fonctionnent")
