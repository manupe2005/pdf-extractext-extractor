"""Dominio puro: checksum SHA-256 sobre bytes originales (Issue #3).

Función sin efectos secundarios ni dependencias de infraestructura:
recibe los bytes originales del documento (sin transformar) y devuelve
su digest SHA-256 como string hexadecimal lowercase de 64 caracteres,
formato contractual que espera el servicio de Persistence.
"""

import hashlib


def compute_sha256(data: bytes) -> str:
    """Calcula el SHA-256 de `data` y lo devuelve como hex digest.

    Args:
        data: Bytes originales del documento, sin transformar.

    Returns:
        String hexadecimal en minúsculas de exactamente 64 caracteres.
    """
    return hashlib.sha256(data).hexdigest()
