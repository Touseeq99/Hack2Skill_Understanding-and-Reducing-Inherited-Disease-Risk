import pytest
from cryptography.exceptions import InvalidTag
from backend.encryptor import Encryptor


def test_encryptor_encrypt_decrypt_roundtrip():
    enc = Encryptor()
    plaintext = "c.1506A>G (p.Lys502Glu) in HBB; pathogenic"
    record_id = "var_001"
    
    ciphertext = enc.encrypt(plaintext, record_id)
    assert ciphertext != plaintext
    assert isinstance(ciphertext, str)
    
    decrypted = enc.decrypt(ciphertext, record_id)
    assert decrypted == plaintext


def test_encryptor_per_record_isolation():
    enc = Encryptor()
    plaintext = "variant_data_secret"
    cipher_rec1 = enc.encrypt(plaintext, "record_1")
    
    # Trying to decrypt with different record_id must fail authentication
    with pytest.raises(InvalidTag):
        enc.decrypt(cipher_rec1, "record_2")


def test_encryptor_tamper_detection():
    enc = Encryptor()
    plaintext = "sensitive_clinical_info"
    record_id = "rec_tamper_test"
    ciphertext = enc.encrypt(plaintext, record_id)
    
    # Mutate ciphertext
    import base64
    raw = bytearray(base64.b64decode(ciphertext))
    raw[-1] ^= 0x01  # flip one bit
    tampered_b64 = base64.b64encode(raw).decode()
    
    with pytest.raises(InvalidTag):
        enc.decrypt(tampered_b64, record_id)
