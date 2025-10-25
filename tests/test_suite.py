import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.anyio
async def test_suite_endpoints():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        payload = {"url":"https://en.wikipedia.org/wiki/Artificial_intelligence"}
        for ep in ("/v1/parse","/v1/metadata","/v1/summary","/v1/preview"):
            r = await ac.post(ep, json=payload)
            assert r.status_code in (200, 304)
            if r.status_code == 200:
                data = r.json()
                assert "url" in data

@pytest.mark.anyio
async def test_suite_endpoints():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        payload = {"url": "https://en.wikipedia.org/wiki/Artificial_intelligence"}
        for ep in ("/v1/parse", "/v1/metadata", "/v1/summary", "/v1/preview"):
            r = await ac.post(ep, json=payload)
            assert r.status_code in (200, 304)

@pytest.mark.anyio
async def test_error_responses():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # 400: Invalid URL
        r = await ac.post("/v1/parse", json={"url": "not-a-url"})
        assert r.status_code == 400
        assert "error" in r.json()
        assert r.json()["error"]["status"] == 400

        # 404: Unknown route
        r = await ac.get("/v1/unknown")
        assert r.status_code == 404
        assert "error" in r.json()
        assert r.json()["error"]["status"] == 404

@pytest.mark.anyio
async def test_rate_limit():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        payload = {"url": "https://example.com"}
        # Exceed rate limit
        for _ in range(15):  # More than RATE_LIMIT_PER_MIN
            r = await ac.post("/v1/parse", json=payload)
            if r.status_code == 429:
                break
        assert r.status_code == 429
        assert "error" in r.json()
        assert r.json()["error"]["status"] == 429

@pytest.mark.anyio
async def test_etag_and_cache():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        url = "https://example.com/test"
        payload = {"url": url}

        # First request
        r1 = await ac.post("/v1/parse", json=payload)
        assert r1.status_code == 200
        assert "ETag" in r1.headers
        assert "Cache-Control" in r1.headers
        etag = r1.headers["ETag"]

        # Second request with If-None-Match
        r2 = await ac.post("/v1/parse", json=payload, headers={"If-None-Match": etag})
        assert r2.status_code == 304
