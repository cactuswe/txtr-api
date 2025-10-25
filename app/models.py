from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import AnyHttpUrl, BaseModel, Field


class ParseRequest(BaseModel):
    """Request model for URL parsing."""
    
    url: AnyHttpUrl

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://example.com/article/123"
                }
            ]
        }
    }


class Sentiment(BaseModel):
    """Sentiment analysis result."""
    
    label: Literal["negative", "neutral", "positive"]
    score: Annotated[float, Field(ge=-1.0, le=1.0)]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "positive",
                    "score": 0.8
                }
            ]
        }
    }


class ParseResponseMeta(BaseModel):
    """Metadata for parse response."""
    
    fetched_at: datetime
    parser: str
    elapsed_ms: int
    cache: bool


class ParseResponse(BaseModel):
    """Response model for parsed URL content."""
    
    url: AnyHttpUrl
    title: str
    text: str
    word_count: int
    language: str
    published_at: Optional[datetime] = None
    lead_image_url: Optional[AnyHttpUrl] = None
    summary: str
    keywords: list[str]
    sentiment: Sentiment
    meta: ParseResponseMeta

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://example.com/article/123",
                    "title": "Example Article",
                    "text": "This is the main content of the article...",
                    "word_count": 150,
                    "language": "en",
                    "published_at": "2025-10-24T12:00:00Z",
                    "lead_image_url": "https://example.com/images/lead.jpg",
                    "summary": "A brief summary of the article content...",
                    "keywords": ["example", "article", "content"],
                    "sentiment": {
                        "label": "positive",
                        "score": 0.8
                    },
                    "meta": {
                        "fetched_at": "2025-10-24T12:01:00Z",
                        "parser": "trafilatura",
                        "elapsed_ms": 450,
                        "cache": False
                    }
                }
            ]
        }
    }


class ErrorDetail(BaseModel):
    """Error details model."""
    
    type: str
    message: str
    status: int
    details: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Error response model."""
    
    error: ErrorDetail

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": {
                        "type": "validation_error",
                        "message": "Invalid URL format",
                        "status": 400,
                        "details": {
                            "field": "url",
                            "reason": "URL must be absolute and contain scheme"
                        }
                    }
                }
            ]
        }
    }


class MetadataResponse(BaseModel):
    """Compact metadata projection for a parsed URL."""

    url: AnyHttpUrl
    title: str
    language: Optional[str] = None
    published_at: Optional[datetime] = None
    lead_image_url: Optional[AnyHttpUrl] = None
    word_count: int
    site: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
                    "title": "Artificial intelligence - Wikipedia",
                    "language": "en",
                    "published_at": "2025-10-24T12:00:00Z",
                    "lead_image_url": "https://upload.wikimedia.org/..../ai.png",
                    "word_count": 15420,
                    "site": "wikipedia.org",
                }
            ]
        }
    }


class SummaryResponse(BaseModel):
    url: AnyHttpUrl
    title: str
    summary: str
    keywords: list[str]
    sentiment: Sentiment
    language: Optional[str] = None
    site: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://www.bbc.com/news/articles/cze61zg7zzpo",
                    "title": "Example BBC article",
                    "summary": "Short summary of the article...",
                    "keywords": ["climate change", "policy", "emissions"],
                    "sentiment": {"label": "neutral", "score": 0.0},
                    "language": "en",
                    "site": "bbc.com",
                }
            ]
        }
    }


class PreviewResponse(BaseModel):
    url: AnyHttpUrl
    title: str
    snippet: str
    lead_image_url: Optional[AnyHttpUrl] = None
    published_at: Optional[datetime] = None
    site: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
                    "title": "Artificial intelligence - Wikipedia",
                    "snippet": "Artificial intelligence (AI) is intelligence demonstrated by machines...",
                    "lead_image_url": "https://upload.wikimedia.org/..../ai.png",
                    "published_at": "2025-10-24T12:00:00Z",
                    "site": "wikipedia.org",
                }
            ]
        }
    }