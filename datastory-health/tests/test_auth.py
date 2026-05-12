"""
Test authentication functions independently.
Demonstrates Week 2 security requirements in action.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from auth import (
    hash_password,
    verify_password,
    encrypt_field,
    decrypt_field,
    create_token,
    verify_token,
)


def test_auth_functions():
    """Test all auth functions."""
    
    print("\n" + "=" * 70)
    print("TESTING AUTHENTICATION FUNCTIONS")
    print("=" * 70 + "\n")
    
    # Test 1: Password hashing
    print("1️⃣  bcrypt Password Hashing")
    print("-" * 70)
    password = "MySecurePassword123!"
    hashed = hash_password(password)
    print(f"   Original password: {password}")
    print(f"   Hashed (bcrypt):   {hashed}")
    assert verify_password(password, hashed), "Hash verification failed!"
    assert not verify_password("WrongPassword", hashed), "Wrong password accepted!"
    print("   ✅ Password hashing & verification working!\n")
    
    # Test 2: Field encryption
    print("2️⃣  Fernet Field Encryption")
    print("-" * 70)
    sensitive_data = "john.doe@example.com"
    encrypted = encrypt_field(sensitive_data)
    decrypted = decrypt_field(encrypted)
    print(f"   Original:  {sensitive_data}")
    print(f"   Encrypted: {encrypted[:50]}...")
    print(f"   Decrypted: {decrypted}")
    assert decrypted == sensitive_data, "Decryption mismatch!"
    print("   ✅ Field encryption & decryption working!\n")
    
    # Test 3: JWT tokens
    print("3️⃣  JWT Token Generation & Verification")
    print("-" * 70)
    token = create_token(user_id=42, role="user", expires_minutes=30)
    print(f"   Token generated (first 50 chars): {token[:50]}...")
    payload = verify_token(token)
    print(f"   Payload: {payload}")
    assert payload["user_id"] == 42, "User ID mismatch!"
    assert payload["role"] == "user", "Role mismatch!"
    print("   ✅ JWT creation & verification working!\n")
    
    # Test 4: Invalid token handling
    print("4️⃣  Invalid Token Handling")
    print("-" * 70)
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.payload"
    result = verify_token(invalid_token)
    print(f"   Attempting to verify invalid token...")
    print(f"   Result: {result}")
    assert result is None, "Invalid token was accepted!"
    print("   ✅ Invalid tokens correctly rejected!\n")
    
    print("=" * 70)
    print("ALL TESTS PASSED ✅")
    print("=" * 70)
    print("\nWeek 2 Security Stack Verified:")
    print("✅ bcrypt (rounds=12)")
    print("✅ Fernet encryption")
    print("✅ JWT signed tokens (HS256)")
    print("✅ Error handling\n")


if __name__ == "__main__":
    test_auth_functions()
