"""Gunicorn: workers por env para aislamiento por procesos y backlog acotado."""

import os

workers = int(os.getenv("WEB_CONCURRENCY", "4"))
worker_class = "uvicorn.workers.UvicornWorker"
bind = f"0.0.0.0:{os.getenv('PORT', '8001')}"
backlog = int(os.getenv("GUNICORN_BACKLOG", "64"))
