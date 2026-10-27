"""Constantes compartidas del servicio."""

# Códigos de error del contrato
INVALID_REQUEST = "INVALID_REQUEST"
INVALID_PDF_CONTENT = "INVALID_PDF_CONTENT"
INTERNAL_ERROR = "INTERNAL_ERROR"
SERVICE_OVERLOADED = "SERVICE_OVERLOADED"

# Content-Types
MULTIPART_FORM_DATA = "multipart/form-data"
MULTIPART_FORM_DATA_BYTES = b"multipart/form-data"

# Problem Details URNs
TYPE_INVALID_REQUEST = "urn:pdf-extractext:invalid-request"
TYPE_INVALID_PDF_CONTENT = "urn:pdf-extractext:invalid-pdf-content"
TYPE_INTERNAL_ERROR = "urn:pdf-extractext:internal-error"
TYPE_SERVICE_OVERLOADED = "urn:pdf-extractext:service-overloaded"

TITLE_INVALID_REQUEST = "Petición inválida"
TITLE_INVALID_PDF_CONTENT = "Contenido PDF inválido"
TITLE_INTERNAL_ERROR = "Error interno del servidor"
TITLE_SERVICE_OVERLOADED = "Servicio saturado"
