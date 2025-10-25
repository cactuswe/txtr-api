from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def mock_html():
    """Sample HTML fixture."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Article</title>
        <meta property="og:image" content="https://example.com/image.jpg">
        <meta property="article:published_time" content="2025-10-24T12:00:00Z">
    </head>
    <body>
        <article>
            <h1>Test Article</h1>
            <p>This is a test article with some sample content. It contains multiple sentences.
            The content is positive and engaging. This should be enough for testing extraction.</p>
        </article>
    </body>
    </html>
    """


@pytest.fixture
def client():
    """TestClient fixture."""
    return TestClient(app)


@patch("app.extractor.fetch_html")
async def test_parse_url(mock_fetch, client, mock_html):
    """Test URL parsing endpoint."""
    # Mock the HTTP response
    mock_fetch.return_value = (mock_html, {
        "content-type": "text/html",
        "server": "test-server"
    })
    
    # Make request
    response = client.post(
        "/v1/parse",
        json={"url": "https://example.com/test"}
    )
    
    # Check response
    assert response.status_code == 200
    data = response.json()
    
    # Check basic fields
    assert data["url"] == "https://example.com/test"
    assert "Test Article" in data["title"]
    assert "test article" in data["text"].lower()
    assert data["word_count"] > 0
    assert data["language"] != "und"
    assert data["lead_image_url"] == "https://example.com/image.jpg"
    
    # Check enrichments
    assert isinstance(data["keywords"], list)
    assert len(data["keywords"]) > 0
    assert len(data["summary"]) > 0
    
    # Check sentiment
    assert "sentiment" in data
    assert data["sentiment"]["label"] in ["positive", "neutral", "negative"]
    assert isinstance(data["sentiment"]["score"], float)
    
    # Check metadata
    assert "meta" in data
    assert isinstance(data["meta"]["fetched_at"], str)
    assert data["meta"]["parser"] == "trafilatura"
    assert isinstance(data["meta"]["elapsed_ms"], int)
    assert data["meta"]["cache"] is False


def test_parse_invalid_url(client):
    """Test parsing with invalid URL."""
    response = client.post(
        "/v1/parse",
        json={"url": "not-a-url"}
    )
    assert response.status_code == 422
    data = response.json()
    assert "error" in data["detail"][0]["msg"].lower()