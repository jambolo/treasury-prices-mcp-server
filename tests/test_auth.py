"""Auth middleware tests using httpx against the full ASGI app."""
from __future__ import annotations

import os
import pytest
from httpx import AsyncClient, ASGITransport


TOKEN = "test-secret-token"


@pytest.fixture(autouse=True)
def set_auth_env(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", TOKEN)


@pytest.fixture
def app():
    # Re-import to pick up the env var set by monkeypatch.
    import importlib
    import server as srv
    importlib.reload(srv)
    return srv.app


@pytest.mark.asyncio
async def test_valid_token_passes(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code != 401


@pytest.mark.asyncio
async def test_wrong_token_rejected(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/", headers={"Authorization": "Bearer wrongtoken"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_missing_token_rejected(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_malformed_bearer_rejected(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/mcp/", headers={"Authorization": TOKEN})  # Missing "Bearer "
    assert r.status_code == 401
