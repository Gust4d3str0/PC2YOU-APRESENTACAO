FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY api-orcamentos/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api-orcamentos/ .
COPY services/ai/ ./ai/
COPY services/product_matching/ ./product_matching/

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"

CMD ["python", "entrypoint.py"]
