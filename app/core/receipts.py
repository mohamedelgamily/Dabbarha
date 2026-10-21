"""AES-256-GCM receipt envelope using PyCryptodomex's authenticated API."""
from Cryptodome.Cipher import AES


class ReceiptCipher:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("Receipt encryption requires a 256-bit key")
        self.key = key

    def cipher(self, nonce, aad):
        if len(nonce) != 12:
            raise ValueError("Receipt nonce must be 96 bits")
        cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce, mac_len=16)
        cipher.update(aad)
        return cipher

    def encrypt(self, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
        ciphertext, tag = self.cipher(nonce, aad).encrypt_and_digest(plaintext)
        return ciphertext + tag

    def decrypt(self, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        if len(ciphertext) < 16 or len(ciphertext) > 8192:
            raise ValueError("Invalid receipt envelope")
        return self.cipher(nonce, aad).decrypt_and_verify(ciphertext[:-16], ciphertext[-16:])
