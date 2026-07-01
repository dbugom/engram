FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    SCHEMA_PATH=/app/db/schema.sql \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src ./src
COPY db ./db

EXPOSE 8000
CMD ["python", "-m", "openbrain.server"]
