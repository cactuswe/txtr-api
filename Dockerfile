# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NLTK_DATA=/usr/local/share/nltk_data

# System deps 
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app


COPY requirements.txt .
RUN pip install -r requirements.txt


COPY app ./app

ENV PYTHONPATH=/app


RUN python - <<'PY' || true
import nltk
pkgs = ["vader_lexicon","stopwords","punkt"]
for p in pkgs:
    try:
        print("Downloading:", p)
        nltk.download(p, quiet=True, raise_on_error=False)
    except Exception as e:
        print("WARN: NLTK download failed for", p, e)
PY

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
