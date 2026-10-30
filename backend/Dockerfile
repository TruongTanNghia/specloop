# Build context: thư mục gốc specloop/ (cần cả backend/ và SpecLoop-Bench/)
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt
COPY backend/app /app/app
COPY backend/experiments.example.yaml /app/experiments.example.yaml
COPY SpecLoop-Bench /SpecLoop-Bench
ENV BENCH_DIR=/SpecLoop-Bench DATA_DIR=/data DATABASE_URL=sqlite:////data/specloop.db
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
