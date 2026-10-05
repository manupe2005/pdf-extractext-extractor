"""Configuración de Gunicorn (Issue #6): workers parametrizables y backlog acotado.

Los workers Uvicorn dan aislamiento por procesos ante el GIL; el backlog
acotado hace fail-fast la acumulación a nivel socket, coherente con el
rechazo 503 del control de admisión.
"""

import os

workers = int(os.getenv("WEB_CONCURRENCY", "4"))
worker_class = "uvicorn.workers.UvicornWorker"
bind = f"0.0.0.0:{os.getenv('PORT', '8001')}"
backlog = int(os.getenv("GUNICORN_BACKLOG", "64"))
