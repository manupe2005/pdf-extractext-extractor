"""Tests de dominio: checksum SHA-256 sobre bytes originales (Issue #3).

Cubre:
1. Vector conocido contra la función pura `compute_sha256`.
2. Formato estricto de salida: str, lowercase, exactamente 64 hex.
"""

from pdf_extractext_extractor.checksum import compute_sha256

# ── Contrato cruzado con Juan Manuel ──────────────────────────────────────
# VECTOR ACORDADO: bytes de entrada `b"test"` y su SHA-256 esperado.
# Este par es el fixture compartido entre Extractor y Persistence para
# validar interoperabilidad. NO modificar sin consenso con Juan Manuel.
SHARED_VECTOR_INPUT = b"test"
SHARED_VECTOR_EXPECTED = (
    "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
)


def test_compute_sha256_matches_known_vector() -> None:
    """El vector compartido con Juan Manuel debe reproducirse exactamente."""
    assert compute_sha256(SHARED_VECTOR_INPUT) == SHARED_VECTOR_EXPECTED


def test_compute_sha256_output_format() -> None:
    """Formato que espera Persistence: str hex lowercase de 64 caracteres."""
    digest = compute_sha256(SHARED_VECTOR_INPUT)

    assert isinstance(digest, str)
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(char in "0123456789abcdef" for char in digest)
