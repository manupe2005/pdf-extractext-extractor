"""Checksum SHA-256 sobre los bytes originales del documento.

El digest hexadecimal lowercase de 64 caracteres es el formato contractual
que espera el servicio de Persistence.
"""

import hashlib


class SHA256ChecksumCalculator:
    """Adaptador concreto que implementa ChecksumCalculator usando hashlib."""

    def calculate(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


def compute_sha256(data: bytes) -> str:
    """Función wrapper para mantener compatibilidad hacia atrás."""
    return SHA256ChecksumCalculator().calculate(data)
