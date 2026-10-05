"""Excepciones de dominio del servicio de extracción."""


class InvalidPDFContentError(Exception):
    """El contenido recibido no es un PDF válido o procesable (mapea a 422)."""


class InternalProcessingError(Exception):
    """Fallo inesperado de la biblioteca de extracción (mapea a 500)."""
