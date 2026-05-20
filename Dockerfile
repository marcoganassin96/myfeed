FROM python:3.12-slim
WORKDIR /app
COPY requirements-fargate.txt .
RUN pip install --no-cache-dir -r requirements-fargate.txt
COPY src/ ./src/
COPY config/ ./config/
WORKDIR /app/src
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]
