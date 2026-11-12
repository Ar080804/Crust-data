FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RUN_WORKER_IN_API=0
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/__init__.py backend/worker.py ./backend/
COPY backend/app/ ./backend/app/
COPY backend/integrations/__init__.py backend/integrations/crustdata.py backend/integrations/pool.py backend/integrations/synonyms.py backend/integrations/telegram.py ./backend/integrations/
CMD ["python", "-m", "backend.worker"]
