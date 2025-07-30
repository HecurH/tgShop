FROM python:3.11-slim

WORKDIR /src/

ENV LANG=C.UTF-8 \
    LANGUAGE=ru_RU:en_US \
    LC_ALL=C.UTF-8

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir --no-warn-script-location --root-user-action -r requirements.txt