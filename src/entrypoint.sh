#!/bin/sh

if [ "$APP_SERVER" = "gunicorn" ]; then
  echo "Starting with gunicorn..."
  exec gunicorn run:main \
    -k aiohttp.worker.GunicornWebWorker \
    -w ${WORKERS:-2} \
    -b ${WEB_SERVER_HOST:-0.0.0.0}:${WEB_SERVER_PORT:-80} \
    --timeout 30 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 2000 \
    --max-requests-jitter 100
else
  echo "Starting with aiohttp..."
  exec python /src/run.py
fi
