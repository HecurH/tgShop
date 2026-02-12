FROM python:3.13-slim

WORKDIR /src/

COPY requirements.txt .
COPY libs/ ./libs/

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN python -m pip install --root-user-action ignore --upgrade pip \
    && python -m pip install --no-cache-dir --no-warn-script-location --root-user-action ignore -r requirements.txt