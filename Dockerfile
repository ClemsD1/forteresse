FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/uploads && chown -R app:app /app

USER app
EXPOSE 5000

CMD ["sh", "-c", "flask --app wsgi init-db && waitress-serve --listen=0.0.0.0:5000 wsgi:app"]
