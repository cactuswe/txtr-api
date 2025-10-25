# URL Insights Mini

A FastAPI-based service that extracts and enriches web articles into structured JSON. Analyzes content for summaries, keywords, sentiment, and more.

## Features

- Article text extraction with metadata
- Content summarization
- Keyword extraction
- Language detection
- Sentiment analysis
- In-memory caching
- Rate limiting
- Docker support

## Installation

### Using pip

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Download required NLTK data
python -m nltk.downloader vader_lexicon stopwords punkt
```

### Using Poetry

```bash
poetry install
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```ini
APP_HOST=0.0.0.0          # Server host
APP_PORT=8000             # Server port
LOG_LEVEL=INFO            # Logging level
HTTP_TIMEOUT_S=12         # HTTP request timeout
USER_AGENT=url-insights-mini/1.0
CACHE_TTL_S=600          # Cache TTL in seconds
RATE_LIMIT_PER_MIN=60    # Rate limit per IP
```

## Running

### Development

```bash
uvicorn app.main:app --reload
```

OpenAPI documentation available at: http://localhost:8000/docs

### Production (Docker)

```bash
# Build image
docker build -t url-insights-mini .

# Run container
docker run -p 8000:8000 url-insights-mini
```

## Usage Example

```bash
curl -X POST http://localhost:8000/v1/parse \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article"}'
```

Example response:
```json
{
  "url": "https://example.com/article",
  "title": "Example Article",
  "text": "Article content...",
  "word_count": 150,
  "language": "en",
  "summary": "Brief summary...",
  "keywords": ["key", "words"],
  "sentiment": {
    "label": "positive",
    "score": 0.8
  },
  "meta": {
    "fetched_at": "2025-10-24T12:00:00Z",
    "parser": "trafilatura",
    "elapsed_ms": 450,
    "cache": false
  }
}
```

## Limitations

- No robots.txt checking in v1
- In-memory cache only (resets on restart)
- English-optimized text analysis
- Rate limiting per IP (no user authentication)

## Development

Run tests:
```bash
pytest -v
```

Format code:
```bash
black .
ruff check --fix .
```

## RapidAPI-only access

This deployment can be configured to accept requests only via the RapidAPI proxy. When enabled, the service enforces that requests include RapidAPI headers and a proxy secret. Configuration is done via environment variables (see `.env.example`).

Behavior when RAPIDAPI_ENFORCE=true:
- All requests must include `X-RapidAPI-Key` header (401 if missing).
- Requests must include `X-RapidAPI-Proxy-Secret` matching `RAPIDAPI_PROXY_SECRET` (403 if incorrect or missing).
- If `RAPIDAPI_HOST` is set, `X-RapidAPI-Host` must match (403 if mismatch).
- Direct requests to the server without Rapid headers will be rejected with 403.

Plan-based behaviour:
- Requests carrying RapidAPI plan headers (e.g. `X-RapidAPI-Plan` or `X-RapidAPI-Subscription`) with the string `free` will have reduced enrichment limits (top_k=8, max_chars=3000).
- Pro/Business plans use higher limits (top_k=12, default max chars from settings).

Logging:
- Structured logs include `rapid_user`, `rapid_plan` and `rapid_host` when available.

To enable RapidAPI-only access, copy `.env.example` to `.env` and set `RAPIDAPI_ENFORCE=true`, `RAPIDAPI_PROXY_SECRET`, and `RAPIDAPI_HOST` as appropriate.
