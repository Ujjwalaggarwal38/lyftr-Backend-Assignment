import os
import json
import hmac
import hashlib
import pytest
from fastapi.testclient import TestClient


def sign_body(secret: str, body_dict: dict) -> tuple[str, bytes]:
    raw = json.dumps(body_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return sig, raw


@pytest.fixture(scope="module")
def client():
    """
    TestClient with isolated database for stats tests.
    """
    os.environ["WEBHOOK_SECRET"] = "testsecret"
    os.environ["DATABASE_URL"] = "sqlite:////./test_stats.db"
    os.environ["LOG_LEVEL"] = "INFO"

    # clean db before tests
    try:
        os.remove("test_stats.db")
    except FileNotFoundError:
        pass

    from app.main import app
    from app.models import init_db

    init_db()

    with TestClient(app) as c:
        yield c

    # cleanup after tests
    try:
        os.remove("test_stats.db")
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


def test_stats_empty_db(client: TestClient):
    res = client.get("/stats")
    assert res.status_code == 200
    body = res.json()

    assert body["total_messages"] == 0
    assert body["senders_count"] == 0
    assert body["messages_per_sender"] == []
    assert body["first_message_ts"] is None
    assert body["last_message_ts"] is None


def test_stats_after_inserts(client: TestClient):
    payloads = [
        {
            "message_id": "s1",
            "from": "+911111111111",
            "to": "+14155550100",
            "ts": "2025-01-15T10:00:00Z",
            "text": "hello",
        },
        {
            "message_id": "s2",
            "from": "+911111111111",
            "to": "+14155550100",
            "ts": "2025-01-15T10:01:00Z",
            "text": "hello again",
        },
        {
            "message_id": "s3",
            "from": "+922222222222",
            "to": "+14155550100",
            "ts": "2025-01-15T10:02:00Z",
            "text": "other sender",
        },
    ]

    for p in payloads:
        r = post_webhook(client, p)
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    res = client.get("/stats")
    assert res.status_code == 200
    body = res.json()

    assert body["total_messages"] == 3
    assert body["senders_count"] == 2
    assert body["first_message_ts"] == "2025-01-15T10:00:00Z"
    assert body["last_message_ts"] == "2025-01-15T10:02:00Z"

    # messages_per_sender must have top sender first
    mps = body["messages_per_sender"]
    assert len(mps) >= 2

    assert mps[0]["from"] == "+911111111111"
    assert mps[0]["count"] == 2

    # second sender
    assert mps[1]["from"] == "+922222222222"
    assert mps[1]["count"] == 1
