import os
import json
import hmac
import hashlib
import pytest
from fastapi.testclient import TestClient


# ----------------------------
# Helpers
# ----------------------------
def sign_body(secret: str, body_dict: dict) -> tuple[str, bytes]:
    raw = json.dumps(body_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return sig, raw


# ----------------------------
# Pytest fixtures
# ----------------------------
@pytest.fixture(scope="module")
def client():
    """
    Creates a test client with isolated DB + secret.
    """
    # Use separate test DB
    os.environ["WEBHOOK_SECRET"] = "testsecret"
    os.environ["DATABASE_URL"] = "sqlite:////./test_app.db"
    os.environ["LOG_LEVEL"] = "INFO"

    try:
        os.remove("test_app.db")
    except FileNotFoundError:
        pass

    from app.main import app
    from app.models import init_db

    init_db()

    with TestClient(app) as c:
        yield c

    # cleanup after tests
    try:
        os.remove("test_app.db")
    except Exception:
        pass


def post_webhook(client: TestClient, payload: dict, secret: str = "testsecret"):
    sig, raw = sign_body(secret, payload)
    return client.post(
        "/webhook",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature": sig,
        },
    )


# ----------------------------
# Tests
# ----------------------------
def test_messages_list_basic(client: TestClient):
    # Insert messages
    payloads = [
        {
            "message_id": "m1",
            "from": "+919876543210",
            "to": "+14155550100",
            "ts": "2025-01-15T10:00:00Z",
            "text": "Hello world",
        },
        {
            "message_id": "m2",
            "from": "+919876543210",
            "to": "+14155550100",
            "ts": "2025-01-15T10:01:00Z",
            "text": "Second message",
        },
        {
            "message_id": "m3",
            "from": "+918888888888",
            "to": "+14155550100",
            "ts": "2025-01-15T10:02:00Z",
            "text": "Other sender",
        },
    ]

    for p in payloads:
        r = post_webhook(client, p)
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    # Fetch messages
    res = client.get("/messages")
    assert res.status_code == 200

    data = res.json()
    assert "data" in data
    assert "total" in data
    assert data["total"] >= 3
    assert data["limit"] == 50
    assert data["offset"] == 0

    # Must include the inserted message_ids
    got_ids = [m["message_id"] for m in data["data"]]
    assert "m1" in got_ids
    assert "m2" in got_ids
    assert "m3" in got_ids


def test_messages_ordering(client: TestClient):
    res = client.get("/messages?limit=10&offset=0")
    assert res.status_code == 200
    data = res.json()["data"]

    # verify deterministic ordering: ts ASC, message_id ASC
    # We'll just check the order among m1,m2,m3
    subset = [m for m in data if m["message_id"] in ["m1", "m2", "m3"]]
    ids = [m["message_id"] for m in subset]
    assert ids == ["m1", "m2", "m3"]


def test_messages_pagination(client: TestClient):
    res1 = client.get("/messages?limit=1&offset=0")
    assert res1.status_code == 200
    body1 = res1.json()
    assert body1["limit"] == 1
    assert body1["offset"] == 0
    assert len(body1["data"]) == 1

    res2 = client.get("/messages?limit=1&offset=1")
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["limit"] == 1
    assert body2["offset"] == 1
    assert len(body2["data"]) == 1

    # first page and second page should not be same record
    assert body1["data"][0]["message_id"] != body2["data"][0]["message_id"]


def test_messages_filter_from(client: TestClient):
    # Filter from=+919876543210 should return m1,m2 (at least)
    res = client.get("/messages?from=%2B919876543210")
    assert res.status_code == 200
    body = res.json()

    ids = [m["message_id"] for m in body["data"]]
    assert "m1" in ids
    assert "m2" in ids
    assert "m3" not in ids


def test_messages_search_q(client: TestClient):
    res = client.get("/messages?q=hello")
    assert res.status_code == 200
    body = res.json()

    ids = [m["message_id"] for m in body["data"]]
    assert "m1" in ids
    # others should not match "hello"
    assert "m2" not in ids
    assert "m3" not in ids


def test_messages_filter_since(client: TestClient):
    # since should include messages >= given ts
    res = client.get("/messages?since=2025-01-15T10:01:00Z")
    assert res.status_code == 200
    body = res.json()

    ids = [m["message_id"] for m in body["data"]]
    assert "m1" not in ids
    assert "m2" in ids
    assert "m3" in ids


def test_messages_limit_validation(client: TestClient):
    # limit must be <= 100
    res = client.get("/messages?limit=101")
    assert res.status_code == 422
