FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/services
RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /data/telegram && chown -R app:app /app /data/telegram
USER app
CMD ["python", "-m", "services.telegram_collector.collector", "listen", "--import-history"]
