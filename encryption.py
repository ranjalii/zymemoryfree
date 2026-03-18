"""encryption.py - Content encryption for memories

Uses Fernet (AES-128-CBC + HMAC-SHA256) for encrypting memory content.
Vectors remain in plaintext for fast semantic search.
"""
import os
import hashlib
import base64
from typing import Optional
from cryptography.fernet import Fernet


class MemoryEncryption:
    """Handles encryption/decryption of memory content."""

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize encryption.

        Args:
            master_key: Base64-encoded 32-byte key. If None, reads from env or disables encryption.
        """
        self.master_key = master_key or os.getenv("ENCRYPTION_KEY", "")
        self.enabled = bool(self.master_key)

        if self.enabled:
            try:
                # Derive Fernet key from master key
                key_bytes = base64.urlsafe_b64decode(self.master_key)
                if len(key_bytes) != 32:
                    raise ValueError("Encryption key must be 32 bytes")
                self.fernet = Fernet(self.master_key.encode() if isinstance(self.master_key, str) else self.master_key)
            except Exception as e:
                print(f"Warning: Invalid encryption key, disabling encryption: {e}")
                self.enabled = False
                self.fernet = None
        else:
            self.fernet = None
            print("Warning: No encryption key set. Content will be stored in plaintext.")

    def encrypt(self, text: str) -> str:
        """
        Encrypt text.

        Args:
            text: Plaintext string

        Returns:
            Encrypted string (or original if encryption disabled)
        """
        if not self.enabled or not text:
            return text

        try:
            return self.fernet.encrypt(text.encode()).decode()
        except Exception as e:
            print(f"Encryption error: {e}")
            return text

    def decrypt(self, encrypted_text: str) -> str:
        """
        Decrypt text.

        Args:
            encrypted_text: Encrypted string

        Returns:
            Plaintext string (or original if encryption disabled)
        """
        if not self.enabled or not encrypted_text:
            return encrypted_text

        try:
            return self.fernet.decrypt(encrypted_text.encode()).decode()
        except Exception as e:
            # Might be plaintext from before encryption was enabled
            print(f"Decryption error (might be plaintext): {e}")
            return encrypted_text

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new encryption key.

        Returns:
            Base64-encoded 32-byte key
        """
        return Fernet.generate_key().decode()


def generate_encryption_key() -> str:
    """
    Generate a new encryption key for the .env file.

    Returns:
        Base64-encoded 32-byte key
    """
    return MemoryEncryption.generate_key()


if __name__ == "__main__":
    # Generate a new key
    key = generate_encryption_key()
    print("Generated encryption key:")
    print(f"ENCRYPTION_KEY={key}")
    print("\nAdd this to your .env file to enable encryption.")
    print("\n⚠️  IMPORTANT: Keep this key secret and backed up!")
    print("    If you lose this key, encrypted data cannot be recovered.")
