"""Genera el par de claves VAPID para las notificaciones push.

Uso: python scripts/generate_vapid_keys.py  → copiá las dos líneas al .env (la privada es un secreto).
"""
from typing import Any
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def generate() -> tuple[Any, ...]:
    """(pública, privada) en base64url: punto P-256 sin comprimir y el escalar privado de 32 bytes."""
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    private = key.private_numbers().private_value.to_bytes(32, 'big')
    return _b64(public), _b64(private)


if __name__ == '__main__':
    pub, priv = generate()
    print(f'VAPID_PUBLIC_KEY={pub}')
    print(f'VAPID_PRIVATE_KEY={priv}')
