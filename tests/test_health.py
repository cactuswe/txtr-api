from fastapi.testclient import TestClient

from app.main import app


def test_health_check():
    """Test health check endpoint."""
    client = TestClient(app)
    response = client.get("/v1/health")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "status" in data
    assert data["status"] == "ok"
    assert "version" in data
    assert data["version"] == "1.0.0"
    assert "uptime_s" in data
    assert isinstance(data["uptime_s"], int)
    assert data["uptime_s"] >= 0