"""Dominio puro: checksum SHA-256 sobre bytes originales (Issue #3).

Función sin efectos secundarios ni dependencias de infraestructura:
recibe los bytes originales del documento (sin transformar) y devuelve
su digest SHA-256 como string hexadecimal lowercase de 64 caracteres,
formato contractual que espera el servicio de Persistence.
"""

import hashlib


class SHA256ChecksumCalculator:
    """Adaptador concreto que implementa ChecksumCalculator usando hashlib."""

    def calculate(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


# Mantener función por compatibilidad hacia atrás
def compute_sha256(data: bytes) -> str:
    """Función wrapper para mantener compatibilidad hacia atrás."""
    return SHA256ChecksumCalculator().calculate(data)
