import os
import hmac
import hashlib
from typing import Optional, Tuple
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ServerCryptoManager:
    AES_KEY_SIZE = 32
    GCM_NONCE_SIZE = 12

    @classmethod
    def generate_ecdh_keys(cls, binding_key: bytes) -> Tuple[bytes, bytes, bytes]:
        server_private_key = ec.generate_private_key(ec.SECP256R1())
        server_public_key = server_private_key.public_key()

        private_value = server_private_key.private_numbers().private_value
        server_private_bytes = private_value.to_bytes(32, byteorder="big")

        server_public_bytes = server_public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )

        server_hmac_bytes = hmac.new(binding_key, server_public_bytes, hashlib.sha256).digest()

        return server_private_bytes, server_public_bytes, server_hmac_bytes

    @classmethod
    def derive_master_key(
        cls, pi_public_bytes: bytes, pi_hmac_bytes: bytes, server_private_bytes: bytes, binding_key: bytes
    ) -> Optional[bytes]:
        try:
            expected_pi_hmac = hmac.new(binding_key, pi_public_bytes, hashlib.sha256).digest()
            if not hmac.compare_digest(expected_pi_hmac, pi_hmac_bytes):
                print("Device HMAC verification failed.")
                return None

            pi_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256R1(),
                pi_public_bytes,
            )

            private_value = int.from_bytes(server_private_bytes, byteorder="big")
            server_private_key = ec.derive_private_key(private_value, ec.SECP256R1())

            shared_secret = server_private_key.exchange(
                ec.ECDH(),
                pi_public_key,
            )

            hkdf = HKDF(
                algorithm=hashes.SHA256(),
                length=cls.AES_KEY_SIZE,
                salt=None,
                info=b"smartlock-master-key",
            )
            master_key = hkdf.derive(shared_secret)

            return master_key

        except Exception as e:
            print(f"Error deriving master key: {e}")
            return None

    @classmethod
    def derive_session_key(cls, master_key: bytes, session_salt: bytes) -> bytes:
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=cls.AES_KEY_SIZE,
            salt=session_salt,
            info=b"smartlock-session-key",
        )
        return hkdf.derive(master_key)

    @classmethod
    def encrypt_data(cls, plaintext: bytes, session_key: bytes) -> bytes:
        nonce = os.urandom(cls.GCM_NONCE_SIZE)
        aesgcm = AESGCM(session_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
        return nonce + ciphertext

    @classmethod
    def decrypt_data(cls, ciphertext_with_nonce: bytes, session_key: bytes) -> Optional[bytes]:
        if len(ciphertext_with_nonce) < cls.GCM_NONCE_SIZE + 16:
            return None

        nonce = ciphertext_with_nonce[: cls.GCM_NONCE_SIZE]
        ciphertext = ciphertext_with_nonce[cls.GCM_NONCE_SIZE :]

        aesgcm = AESGCM(session_key)
        return aesgcm.decrypt(nonce, ciphertext, associated_data=None)
