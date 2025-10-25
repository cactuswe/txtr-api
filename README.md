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
