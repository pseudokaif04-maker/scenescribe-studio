import pytest
from starlette.testclient import TestClient

from app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_homepage_serves_the_studio(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "SceneScribe" in response.text
    assert 'id="captionGrid"' in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_health_reports_capabilities_and_choices(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert "version" in payload
    assert isinstance(payload["speech"], bool)
    assert isinstance(payload["ocr"], bool)
    assert payload["max_upload_mb"] > 0
    assert payload["tones"][0]["value"] == "auto"
    assert {"cinematic", "playful", "minimal"} <= {
        item["value"] for item in payload["tones"]
    }
    assert {"instagram", "tiktok", "youtube", "linkedin", "x"} <= {
        item["value"] for item in payload["platforms"]
    }
    for platform in payload["platforms"]:
        assert platform["limit"] > 0


def test_favicon_is_available(client):
    response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in response.content


def test_unknown_api_and_job_return_json_404(client):
    response = client.get("/api/jobs/not-a-real-job")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "error" in response.json()

    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json() == {"error": "Not found."}


def test_analyze_requires_a_video(client):
    response = client.post("/api/analyze", data={"tone": "auto"})
    assert response.status_code == 400
    assert "Choose a video" in response.json()["error"]


def test_analyze_rejects_unrecognised_extensions(client):
    response = client.post(
        "/api/analyze",
        files={"video": ("notes.txt", b"not a video", "text/plain")},
    )
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["error"]


def test_remix_validates_body_and_unknown_job(client):
    response = client.post(
        "/api/jobs/0123456789abcdef0123456789abcdef/remix",
        data="not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400

    response = client.post(
        "/api/jobs/0123456789abcdef0123456789abcdef/remix",
        json={"tone": "chaotic", "platform": "instagram", "seed": 1},
    )
    assert response.status_code == 400
    assert "tone" in response.json()["error"].lower()


def test_frame_route_rejects_path_traversal(client):
    response = client.get(
        "/api/jobs/0123456789abcdef0123456789abcdef/frames/..%2Fsource.mp4"
    )
    assert response.status_code == 404


def test_health_reports_clipforge(client):
    payload = client.get("/api/health").json()
    assert "clipforge" in payload
    clipforge = payload["clipforge"]
    assert isinstance(clipforge["available"], bool)
    assert clipforge["available"] is True
    assert clipforge["reason"] is None
    assert clipforge["home"]
    assert clipforge["max_clips"] >= 1


def test_clip_run_requires_source(client):
    response = client.post("/api/clip-runs", json={})
    assert response.status_code == 400
    assert "paste" in response.json()["error"].lower()


def test_clip_run_rejects_invalid_source(client):
    response = client.post("/api/clip-runs", json={"source": "not-a-link"})
    assert response.status_code == 400
    assert "does not exist" in response.json()["error"].lower()


def test_clip_run_rejects_bad_settings(client):
    response = client.post(
        "/api/clip-runs",
        json={"source": "https://www.youtube.com/watch?v=abc", "count": 0},
    )
    assert response.status_code == 400
    assert "clip count" in response.json()["error"].lower()


def test_unknown_clip_run_routes_return_404(client):
    run_id = "0" * 32
    assert client.get(f"/api/clip-runs/{run_id}").status_code == 404
    assert client.post(f"/api/clip-runs/{run_id}/cancel").status_code == 404
    assert client.post(f"/api/clip-runs/{run_id}/open-folder").status_code == 404
    assert client.post(f"/api/clip-runs/{run_id}/clips/1/caption").status_code == 404
    assert client.get(f"/api/clip-runs/{run_id}/clips/1/thumbnail").status_code == 404
