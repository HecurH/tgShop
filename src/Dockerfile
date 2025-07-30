FROM python:3.10-slim

WORKDIR /src/

ENV LANG=C.UTF-8 \
    LANGUAGE=ru:en \
    LC_ALL=C.UTF-8

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir --no-warn-script-location -r requirements.txt