FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/data/camera_reports /app/data/tts_cache

ENV PORT=8931
ENV PYTHONIOENCODING=utf-8
EXPOSE 8931

CMD ["python", "scripts/demo_server.py", "8931"]
