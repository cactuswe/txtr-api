"""URL Insights API – FastAPI entrypoint"""

from __future__ import annotations

import os
import time
import json
import hashlib
from typing import Any, Dict
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
try:
    from starlette.middleware.proxy_headers import ProxyHeadersMiddleware
except Exception:  # pragma: no cover - optional dependency
    ProxyHeadersMiddleware = None
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.staticfiles import StaticFiles
from pydantic import AnyHttpUrl
from starlette.middleware.base import BaseHTTPMiddleware
import httpx

from .cache import get as cache_get, set as cache_set, size_bytes as cache_size
from . import enrich
from .utils import (
    word_count,
    normalize_text,
    clean_citations_and_spaces,
    elapsed_ms,
    get_request_id,
    validate_url,
    RateLimitError,
)
from .extractor import (
    extract_meta_bs4,
    extract_trafilatura,
    fetch_html,
    find_lead_image,
    merge_extraction,
    extract_lead_image_bs4,
    extract_published_at,
    extract_site_name,
    extract_title_bs4,
)
from .enrich import extract_keywords
from .models import (
    ParseRequest,
    ParseResponse,
    Sentiment,
    ErrorResponse,
    MetadataResponse,
    SummaryResponse,
    PreviewResponse,
)
from .config import settings

# Basic settings
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
CACHE_DIR = os.getenv("CACHE_DIR", "./data/cache")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
DEFAULT_CACHE_TTL_SECONDS = int(os.getenv("DEFAULT_CACHE_TTL_SECONDS", "600"))
PARSER_VERSION = "v1"

# Error Responses (structured)
error_responses = {
    400: {"model": ErrorResponse, "description": "Bad Request - Invalid URL or parameters"},
    404: {"model": ErrorResponse, "description": "Not Found - URL could not be accessed or content not found"},
    429: {"model": ErrorResponse, "description": "Too Many Requests - Rate limit exceeded"},
    500: {"model": ErrorResponse, "description": "Internal Server Error - Server-side error"},
}

# OpenAPI tags + description
TAGS_METADATA = [
    {"name": "Health", "description": "Health check endpoint"},
    {"name": "Core", "description": "Core URL parsing and analysis"},
    {"name": "Utility", "description": "Utility endpoints"},
]

APP_DESCRIPTION = """
URL Insights API

Extract structured data from any webpage URL. The API extracts title, main text,
publication date, lead image, language, summary, keywords and sentiment.

Example cURL:

    curl -X POST 'https://txtr-api.onrender.com/v1/parse' \
      -H 'Content-Type: application/json' \
      -d '{"url":"https://en.wikipedia.org/wiki/Artificial_intelligence"}'

Rate limits: 10 req/min (per IP or API key).

Errors: 400, 404, 429, 500

Optional API key via X-API-Key header increases rate limits.
"""

# Initialize app
app = FastAPI(
    title="URL Insights API",
    version="0.1.0",
    description=APP_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    contact={"name": "Support", "email": "support@example.com"},
    license_info={"name": "MIT"},
)

# uptime
start_time = time.time()

# in-memory token bucket for simple rate limiting
_BUCKET: dict[str, tuple[float, float]] = {}
BURST = max(5, RATE_LIMIT_PER_MIN // 2)


def _allow(ip: str) -> bool:
    now = time.time()
    tokens, ts = _BUCKET.get(ip, (BURST, now))
    refill = (RATE_LIMIT_PER_MIN / 60.0) * (now - ts)
    tokens = min(BURST, tokens + refill)
    if tokens >= 1.0:
        tokens -= 1.0
        _BUCKET[ip] = (tokens, now)
        return True
    _BUCKET[ip] = (tokens, now)
    return False


@app.middleware("http")
async def ratelimit_mw(req: Request, call_next):
    ip = (req.headers.get("x-forwarded-for") or (req.client.host if req.client else "0.0.0.0")).split(",")[0].strip()
    if not _allow(ip):
        return JSONResponse(status_code=429, content={"error": {"type": "rate_limited", "message": "rate limit exceeded", "status": 429}})
    return await call_next(req)


# helpers
def _etag_for(url: str) -> str:
    h = hashlib.blake2b(f"{url}|{PARSER_VERSION}".encode(), digest_size=12).hexdigest()
    return f'W/"{h}"'


def _cache_headers(etag: str, ttl: int = DEFAULT_CACHE_TTL_SECONDS) -> dict[str, str]:
    return {"ETag": etag, "Cache-Control": f"public, max-age={ttl}"}


def _enforce_cache_budget() -> None:
    try:
        if cache_size(CACHE_DIR) > int(os.getenv("CACHE_MAX_BYTES", "104857600")):
            pass
    except Exception:
        pass


# Core parse orchestrator
async def core_parse(url_str: str) -> dict[str, Any]:
    start = time.perf_counter()

    html, headers = await fetch_html(
        url=url_str,
        timeout_s=int(os.getenv("HTTP_TIMEOUT_SECS", "12")),
        user_agent=os.getenv("USER_AGENT", "url-insights-mini/1.0"),
    )
    if "text/html" not in headers.get("content-type", "").lower():
        raise HTTPException(status_code=415, detail="unsupported content-type")

    content = extract_trafilatura(html, url_str)
    meta_data = extract_meta_bs4(html)
    data, used_bs4_fallback = merge_extraction(content, meta_data, html, url_str)

    text = clean_citations_and_spaces(normalize_text(data.get("text", "")))
    if not text or word_count(text) < 10:
        raise HTTPException(status_code=422, detail="parse_failed: too little text extracted")

    title = data.get("title") or extract_title_bs4(html) or ""
    lead_image_url = data.get("image") or extract_lead_image_bs4(html, url_str)
    published_at, published_sources = extract_published_at(html)
    site = extract_site_name(html, url_str)

    max_chars = int(os.getenv("MAX_ENRICH_CHARS", "6000"))
    enrich_text = text[:max_chars] if len(text) > max_chars else text

    language = enrich.detect_language(enrich_text)
    summary = enrich.summarize_text(enrich_text) or ""
    keywords = extract_keywords(enrich_text, top_k=12)
    sentiment = enrich.analyze_sentiment(summary or text[:3000])

    payload = {
        "url": url_str,
        "title": title or "",
        "text": text,
        "language": language,
        "published_at": published_at,
        "lead_image_url": lead_image_url,
        "word_count": word_count(text),
        "summary": summary or "",
        "keywords": keywords,
        "sentiment": sentiment or {"label": "neutral", "score": 0.0},
        "meta": {
            "site": site,
            "published_sources": published_sources,
            "parser": "trafilatura|bs4" if used_bs4_fallback else "trafilatura",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_ms": elapsed_ms(start),
            "cache": False,
        },
    }

    return payload


# Projections
def _project_metadata(full: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": full.get("url"),
        "title": full.get("title"),
        "language": full.get("language"),
        "published_at": full.get("published_at"),
        "lead_image_url": full.get("lead_image_url"),
        "word_count": full.get("word_count"),
        "site": (full.get("meta") or {}).get("site"),
    }


def _project_summary(full: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": full.get("url"),
        "title": full.get("title"),
        "summary": full.get("summary"),
        "keywords": full.get("keywords") or [],
        "sentiment": full.get("sentiment") or {"label": "neutral", "score": 0.0},
        "language": full.get("language"),
        "site": (full.get("meta") or {}).get("site"),
    }


def _project_preview(full: dict[str, Any]) -> dict[str, Any]:
    text = full.get("summary") or (full.get("text") or "")
    snippet = (text[:280] + "…") if isinstance(text, str) and len(text) > 300 else text
    return {
        "url": full.get("url"),
        "title": full.get("title"),
        "snippet": snippet,
        "lead_image_url": full.get("lead_image_url"),
        "published_at": full.get("published_at"),
        "site": (full.get("meta") or {}).get("site"),
    }


# Static assets for docs
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

SWAGGER_PARAMS = {
    "docExpansion": "list",
    "defaultModelsExpandDepth": 0,
    "defaultModelExpandDepth": 1,
    "tryItOutEnabled": True,
}


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} – Docs",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui.css",
        swagger_ui_parameters=SWAGGER_PARAMS,
    ).replace("</head>", '<link rel="stylesheet" type="text/css" href="/static/swagger.css"></head>')


@app.get("/redoc", include_in_schema=False)
def custom_redoc():
    return get_redoc_html(openapi_url=app.openapi_url, title=f"{app.title} – ReDoc", with_google_fonts=False)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs", status_code=302)


# Routes
@app.get("/v1/health", tags=["Health"], responses={200: {"description": "API is healthy"}, **error_responses})
async def health():
    return {"ok": True}


@app.post(
    "/v1/parse",
    tags=["Core"],
    responses={200: {"model": ParseResponse, "description": "Successful URL parsing and analysis"}, **error_responses},
)
async def parse(req: ParseRequest, request: Request):
    url_str = str(req.url)
    etag = _etag_for(url_str)

    inm = request.headers.get("if-none-match")
    if inm == etag:
        cached = cache_get(CACHE_DIR, url_str)
        if cached and cached.etag == etag:
            return Response(status_code=304)

    cached = cache_get(CACHE_DIR, url_str)
    if cached and cached.etag == etag:
        payload = jsonable_encoder(cached.payload)
        headers = _cache_headers(cached.etag, DEFAULT_CACHE_TTL_SECONDS)
        return JSONResponse(content=payload, headers=headers)

    result = await core_parse(url_str)
    payload = jsonable_encoder(result)

    _enforce_cache_budget()
    try:
        cache_set(CACHE_DIR, url_str, etag, payload, CACHE_TTL_SECONDS)
    except Exception:
        pass

    headers = _cache_headers(etag, DEFAULT_CACHE_TTL_SECONDS)
    return JSONResponse(content=payload, headers=headers)


@app.post("/v1/metadata", tags=["Utility"], responses={200: {"model": MetadataResponse, "description": "Basic URL metadata"}, **error_responses})
async def metadata(req: ParseRequest, request: Request):
    url_str = str(req.url)
    etag = _etag_for(url_str) + "-meta"
    inm = request.headers.get("if-none-match")
    if inm == etag:
        return Response(status_code=304)

    full = await parse(req, request)
    if isinstance(full, Response) and full.status_code == 304:
        return Response(status_code=304)
    data = json.loads(full.body.decode()) if isinstance(full, JSONResponse) else full

    proj = _project_metadata(data)
    headers = _cache_headers(etag, DEFAULT_CACHE_TTL_SECONDS)
    return JSONResponse(content=jsonable_encoder(proj), headers=headers)


@app.post("/v1/summary", tags=["Utility"], responses={200: {"model": SummaryResponse, "description": "URL content summary with keywords"}, **error_responses})
async def summary(req: ParseRequest, request: Request):
    url_str = str(req.url)
    etag = _etag_for(url_str) + "-sum"
    inm = request.headers.get("if-none-match")
    if inm == etag:
        return Response(status_code=304)

    full = await parse(req, request)
    if isinstance(full, Response) and full.status_code == 304:
        return Response(status_code=304)
    data = json.loads(full.body.decode()) if isinstance(full, JSONResponse) else full

    proj = _project_summary(data)
    headers = _cache_headers(etag, DEFAULT_CACHE_TTL_SECONDS)
    return JSONResponse(content=jsonable_encoder(proj), headers=headers)


@app.post("/v1/preview", tags=["Utility"], responses={200: {"model": PreviewResponse, "description": "Preview with title and snippet"}, **error_responses})
async def preview(req: ParseRequest, request: Request):
    url_str = str(req.url)
    etag = _etag_for(url_str) + "-prev"
    inm = request.headers.get("if-none-match")
    if inm == etag:
        return Response(status_code=304)

    full = await parse(req, request)
    if isinstance(full, Response) and full.status_code == 304:
        return Response(status_code=304)
    data = json.loads(full.body.decode()) if isinstance(full, JSONResponse) else full

    proj = _project_preview(data)
    headers = _cache_headers(etag, DEFAULT_CACHE_TTL_SECONDS)
    return JSONResponse(content=jsonable_encoder(proj), headers=headers)


# Exception handlers
@app.exception_handler(RateLimitError)
async def _rate_limit_handler(request: Request, exc: RateLimitError):
    return JSONResponse(status_code=429, content={"error": {"type": "rate_limited", "message": "rate limit exceeded", "status": 429, "details": None}})


@app.exception_handler(httpx.TimeoutException)
async def _timeout_handler(request: Request, exc: httpx.TimeoutException):
    return JSONResponse(status_code=504, content={"error": {"type": "timeout", "message": "upstream timeout", "status": 504, "details": None}})


@app.exception_handler(ValueError)
async def _value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": {"type": "invalid_request", "message": str(exc), "status": 400, "details": None}})


@app.exception_handler(Exception)
async def _fallback_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": {"type": "internal_error", "message": "unexpected error", "status": 500, "details": None}})


# Middlewares: security + request-id + body size
class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            headers = response.headers
            headers.setdefault("X-Content-Type-Options", "nosniff")
            headers.setdefault("Referrer-Policy", "no-referrer")
        except Exception:
            pass
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = get_request_id()
        start = time.perf_counter()
        response = await call_next(request)
        try:
            response.headers.setdefault("X-Request-ID", request_id)
        except Exception:
            pass
        print(json.dumps({
            "ts": int(time.time()),
            "rid": request_id,
            "ip": request.client.host if request.client else "-",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "lat_ms": elapsed_ms(start),
            "user_agent": request.headers.get("user-agent", "-"),
            "referer": request.headers.get("referer", "-"),
        }))
        return response


class BodySizeLimit(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int = 8192):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > self.max_bytes:
            return JSONResponse(status_code=413, content={"error": {"type": "payload_too_large", "message": "body too large", "status": 413, "details": None}})
        return await call_next(request)


app.add_middleware(SecurityMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(BodySizeLimit, max_bytes=16_384)

# Minimal, permissive CORS (tighten before production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag", "X-Request-ID"],
)

# Respect proxy headers (e.g. X-Forwarded-Host, X-Forwarded-Proto) behind proxies like Render
if ProxyHeadersMiddleware is not None:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")


# Custom OpenAPI generation
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Render sets RENDER_EXTERNAL_URL (https://<your-app>.onrender.com)
    external = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("EXTERNAL_BASE_URL")
    if external:
        schema["servers"] = [{"url": external}]
    else:
        # Let Swagger use same-origin by not setting servers at all
        schema.pop("servers", None)

    schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyHeader"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi