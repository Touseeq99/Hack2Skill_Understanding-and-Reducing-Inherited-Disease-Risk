"""Application-level encryption interface using AES-256-GCM with per-record derived keys.

Adheres strictly to the architectural requirement:
'Do NOT use pgsodium. Use an Encryptor interface with application-level AES-GCM
and per-record keys (cryptography package).'
"""

import base64
import os
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


class Encryptor:
    """Manages AES-256-GCM encryption and decryption with per-record key derivation."""

    def __init__(self, master_key_bytes: Optional[bytes] = None):
        if master_key_bytes is None:
            env_key = os.environ.get("MASTER_ENCRYPTION_KEY")
            if env_key:
                try:
                    master_key_bytes = base64.b64decode(env_key)
                except Exception:
                    master_key_bytes = env_key.encode("utf-8")
            else:
                if os.environ.get("APP_ENV", "development").lower() == "production":
                    raise RuntimeError("MASTER_ENCRYPTION_KEY must be set in production; the demo key is not allowed.")
                # Default 32-byte demo key (development only)
                master_key_bytes = b"01234567890123456789012345678901"

        if len(master_key_bytes) < 32:
            master_key_bytes = master_key_bytes.ljust(32, b"0")[:32]
        elif len(master_key_bytes) > 32:
            master_key_bytes = master_key_bytes[:32]

        self._master_key = master_key_bytes

    def _derive_record_key(self, record_id: str) -> bytes:
        """Derive a distinct 256-bit AES key per record using HKDF."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"inherited_disease_risk_platform_salt",
            info=record_id.encode("utf-8"),
        )
        return hkdf.derive(self._master_key)

    def encrypt(self, plaintext: str, record_id: str) -> str:
        """Encrypt plaintext using AES-256-GCM with a per-record derived key.
        
        Returns base64-encoded string: nonce (12 bytes) + ciphertext + tag.
        """
        record_key = self._derive_record_key(record_id)
        aesgcm = AESGCM(record_key)
        nonce = os.urandom(12)
        plaintext_bytes = plaintext.encode("utf-8")
        associated_data = record_id.encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, associated_data)
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode("utf-8")

    def decrypt(self, ciphertext_b64: str, record_id: str) -> str:
        """Decrypt base64-encoded ciphertext using the per-record key.
        
        Raises cryptography.exceptions.InvalidTag on tamper or mismatch.
        """
        raw_combined = base64.b64decode(ciphertext_b64.encode("utf-8"))
        if len(raw_combined) < 12:
            raise ValueError("Ciphertext too short to contain valid nonce.")
        nonce = raw_combined[:12]
        ciphertext = raw_combined[12:]
        record_key = self._derive_record_key(record_id)
        aesgcm = AESGCM(record_key)
        associated_data = record_id.encode("utf-8")
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, associated_data)
        return decrypted_bytes.decode("utf-8")


# Default singleton instance
default_encryptor = Encryptor()

