"""Checksum SHA-256 de los bytes originales del documento."""

import hashlib


def compute_sha256(data: bytes) -> str:
    """Devuelve el SHA-256 de `data` como hex lowercase de 64 caracteres."""
    return hashlib.sha256(data).hexdigest()
