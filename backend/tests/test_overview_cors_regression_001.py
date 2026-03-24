# Regression: ISSUE-001 — Invalid username returns "Failed to fetch" due to missing CORS headers
# Found by /qa on 2026-03-23
# Report: .gstack/qa-reports/qa-report-projects-akshitkalra-com-2026-03-23.md
#
# Root cause: HTTPException responses don't get CORS headers from FastAPI middleware.
# Fix: Use JSONResponse instead so CORS middleware wraps it properly.

from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestOverview404ReturnsCorsCompatibleResponse:
    """Verify that a 404 from /overview returns a JSON body the browser can read.

    Before the fix, HTTPException raised a 404 that FastAPI's CORS middleware
    didn't attach Access-Control-Allow-Origin to, so the browser blocked the
    response entirely and the frontend got "Failed to fetch" instead of the
    actual error message.
    """

    async def test_nonexistent_user_returns_404_with_json_body(self, client):
        with patch("main.fetch_user_games", new_callable=AsyncMock, return_value=([], None)):
            response = await client.post(
                "/overview",
                json={"username": "xxxxxxxxxnotarealuser99999", "months": 1, "speed": "all"},
            )
            assert response.status_code == 404
            body = response.json()
            assert "detail" in body
            assert "xxxxxxxxxnotarealuser99999" in body["detail"]

    async def test_nonexistent_user_response_is_json_not_exception(self, client):
        """Ensure the response is a proper JSONResponse, not an HTTPException.

        JSONResponse gets CORS headers from the middleware; HTTPException doesn't.
        We verify by checking that the content-type is application/json.
        """
        with patch("main.fetch_user_games", new_callable=AsyncMock, return_value=([], None)):
            response = await client.post(
                "/overview",
                json={"username": "nobody", "months": 1, "speed": "all"},
            )
            assert response.status_code == 404
            assert "application/json" in response.headers.get("content-type", "")
