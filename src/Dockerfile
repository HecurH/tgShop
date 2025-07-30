FROM python:3.11-slim

WORKDIR /src/

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir --no-warn-script-location --root-user-action ignore -r requirements.txt