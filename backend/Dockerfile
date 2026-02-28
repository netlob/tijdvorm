FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev libfreetype6-dev ffmpeg libturbojpeg0 && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    playwright install --with-deps chromium

COPY backend/ /app/backend/
COPY assets/ /app/assets/

WORKDIR /app

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
