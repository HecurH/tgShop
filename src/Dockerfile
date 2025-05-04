FROM python:3.10-slim

WORKDIR /src/

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt