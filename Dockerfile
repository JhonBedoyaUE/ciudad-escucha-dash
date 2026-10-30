FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8050

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY data ./data
COPY assets ./assets

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Salud simple vía el servidor (Waitress)
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",8050)}/health')" || exit 1

EXPOSE 8050
CMD ["waitress-serve", "--host=0.0.0.0", "--port=8050", "app:server"]
