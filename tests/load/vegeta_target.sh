#!/bin/bash

set -e

PDF_FILE_PATH="./tests/data/heavy.292.pdf"
PDF_FILENAME="heavy.292.pdf"
PDF_CONTENT_TYPE="application/pdf"

TARGET_URL="http://localhost:8090/extract"

BODY_FILE="./tests/load/vegeta_body.bin"
TARGET_FILE="./tests/load/vegeta_targets.txt"

# Boundary utilizado para construir el multipart
BOUNDARY="------------------------$(date +%s%N)"

if [ ! -f "$PDF_FILE_PATH" ]; then
    echo "ERROR: No existe el archivo '$PDF_FILE_PATH'."
    exit 1
fi

echo "--- Generando body multipart ---"

{
    printf -- "--%s\r\n" "$BOUNDARY"
    printf 'Content-Disposition: form-data; name="file"; filename="%s"\r\n' "$PDF_FILENAME"
    printf "Content-Type: %s\r\n" "$PDF_CONTENT_TYPE"
    printf "\r\n"

    cat "$PDF_FILE_PATH"

    printf "\r\n"
    printf -- "--%s--\r\n" "$BOUNDARY"
} > "$BODY_FILE"

echo "--- Generando target de Vegeta ---"

{
    printf "POST %s\n" "$TARGET_URL"
    printf "Host: extraction.pdf-extractext.localhost\n"
    printf "Content-Type: multipart/form-data; boundary=%s\n" "$BOUNDARY"
} > "$TARGET_FILE"

echo "Body:   $BODY_FILE"
echo "Target: $TARGET_FILE"