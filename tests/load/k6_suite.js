import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// PDF que se utiliza para las pruebas
const PDF_FILE_PATH = '../data/heavy.292.pdf';
const PDF_FILENAME = 'heavy.292.pdf';
const PDF_CONTENT_TYPE = 'application/pdf';

let PDF_BINARY_DATA;

try {
  PDF_BINARY_DATA = open(PDF_FILE_PATH, 'b');
} catch (e) {
  console.error(
    `ERROR: No se pudo abrir el archivo PDF en ${PDF_FILE_PATH}. Asegúrate de que exista.`
  );
  PDF_BINARY_DATA = new ArrayBuffer(1);
}

// Cuerpo multipart construido UNA sola vez en el init context.
// Con 100 VUs y un PDF de 8.5 MB, http.file() armaba una copia del body por
// iteración ~ OOM del proceso k6 (3.3 GB) en hosts con poca RAM. Un único
// ArrayBuffer compartido entre iteraciones elimina esa duplicación.
const MULTIPART_BOUNDARY = '----k6boundary9f4e2c1';
const MULTIPART_BODY = (function buildBody() {
  const head = new TextEncoder().encode(
    `--${MULTIPART_BOUNDARY}\r\n` +
    `Content-Disposition: form-data; name="file"; filename="${PDF_FILENAME}"\r\n` +
    `Content-Type: ${PDF_CONTENT_TYPE}\r\n\r\n`
  );
  const tail = new TextEncoder().encode(`\r\n--${MULTIPART_BOUNDARY}--\r\n`);
  const pdf = new Uint8Array(PDF_BINARY_DATA);
  const body = new Uint8Array(head.length + pdf.length + tail.length);
  body.set(head, 0);
  body.set(pdf, head.length);
  body.set(tail, head.length + pdf.length);
  return body.buffer;
})();

// Métrica para contar errores que NO sean 503
const customErrorRate = new Rate('custom_error_rate_excluding_503');

export const options = {
  scenarios: {
    // Prueba de spike: subir rápidamente hasta 100 usuarios
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 100 },
        { duration: '30s', target: 100 },
        { duration: '5s', target: 0 },
      ],
      tags: { test_type: 'spike' },
      gracefulStop: '2s',
    },

    // Prueba de carga constante: 25 requests por segundo
    arrival_rate_constant: {
      executor: 'constant-arrival-rate',
      rate: 25,
      timeUnit: '1s',
      duration: '60s',
      preAllocatedVUs: 10,
      maxVUs: 100,
      tags: { test_type: 'arrival_rate' },
      gracefulStop: '2s',
      startTime: '50s',
    },
  },

  thresholds: {
    // Los errores distintos de 503 deben ser menores al 1%
    'http_req_failed{status:!503}': ['rate < 0.01'],

    // El 99% de las respuestas debe tardar menos de 2 segundos
    'http_req_duration': ['p(99) < 2000'],

    // Nuestra métrica personalizada de errores distintos de 503
    'custom_error_rate_excluding_503': ['rate < 0.01'],
  },
};

export default function () {
  // Se accede a Extraction a través de Traefik.
  // localhost:8090 es el puerto publicado por Traefik en WSL.
  const url = 'http://localhost:8090/extract';

  const params = {
    headers: {
      Host: 'extraction.pdf-extractext.localhost',
      'Content-Type': `multipart/form-data; boundary=${MULTIPART_BOUNDARY}`,
    },
    // Los bodies de respuesta son JSON pequeños; descartarlos evita retainers.
    responseType: 'text',
  };

  const res = http.post(url, MULTIPART_BODY, params);

  const isSuccess = check(res, {
    'status is 200': (r) => r.status === 200,
  });

  if (!isSuccess && res.status !== 503) {
    customErrorRate.add(1);
  } else {
    customErrorRate.add(0);
  }

  sleep(0.5);
}