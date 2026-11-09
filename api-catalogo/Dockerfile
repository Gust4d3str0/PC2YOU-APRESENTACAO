FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY api-catalogo/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api-catalogo/ .
COPY services/product_matching/ ./product_matching/
COPY services/catalog_specs/ ./catalog_specs/
# Demo endpoints (/demo/telegram-parse) reuse the real Telegram parser: `services.telegram_collector.*`
COPY services/telegram_collector/__init__.py services/telegram_collector/parser.py services/telegram_collector/links.py services/telegram_collector/filters.py ./telegram_collector/
# Sanitized snapshot loaded into an empty database when DEMO_MODE=true
COPY demo-data/ ./demo-data/

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /data/ml && chown -R app:app /app /data/ml

USER app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
