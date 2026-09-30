FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NUANBAN_HOST=0.0.0.0 \
    NUANBAN_PORT=8002 \
    NUANBAN_AUTO_START_MODELS=0

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/backend/requirements.txt

COPY backend /app/backend
COPY web /app/web
COPY train/fetch_paint.py /app/train/fetch_paint.py

EXPOSE 8002

CMD ["python", "backend/run.py"]
