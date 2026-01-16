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
    TestClient with isolated DB for webhook tests.
    """
    os.environ["WEBHOOK_SECRET"] = "testsecret"
    os.environ["DATABASE_URL"] = "sqlite:////./test_webhook.db"
    os.environ["LOG_LEVEL"] = "INFO"

    # clean db before tests
    try:
        os.remove("test_webhook.db")
    except FileNotFoundError:
        pass

    from app.main import app
    from app.models import init_db

    init_db()

    with TestClient(app) as c:
        yield c

    # cleanup after tests
    try:
        os.remove("test_webhook.db")
    except Exception:
        pass


def post_webhook(client: TestClient, payload: dict, secret="testsecret", override_sig=None):
    sig, raw = sign_body(secret, payload)

    if override_sig is not None:
        sig = override_sig

    return client.post(
        "/webhook",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature": sig,
        },
    )


def test_webhook_invalid_signature(client: TestClient):
    payload = {
        "message_id": "w1",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "hello",
    }

    res = post_webhook(client, payload, override_sig="wrong_signature")
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid signature"


def test_webhook_valid_signature_success(client: TestClient):
    payload = {
        "message_id": "w2",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:01:00Z",
        "text": "valid",
    }

    res = post_webhook(client, payload)
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_webhook_duplicate_message_id(client: TestClient):
    payload = {
        "message_id": "dup1",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:05:00Z",
        "text": "first insert",
    }

    res1 = post_webhook(client, payload)
    assert res1.status_code == 200
    assert res1.json() == {"status": "ok"}

    # send again with same message_id -> should still return ok (idempotency)
    res2 = post_webhook(client, payload)
    assert res2.status_code == 200
    assert res2.json() == {"status": "ok"}

    # DB should only have 1 record for this message_id
    # We'll confirm by listing messages
    r = client.get("/messages?from=%2B919876543210")
    assert r.status_code == 200
    ids = [m["message_id"] for m in r.json()["data"]]
    assert ids.count("dup1") == 1


def test_webhook_validation_error(client: TestClient):
    # invalid from number (missing +)
    payload = {
        "message_id": "bad1",
        "from": "919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:10:00Z",
        "text": "bad payload",
    }

    res = post_webhook(client, payload)
    assert res.status_code == 422


def test_webhook_invalid_ts(client: TestClient):
    # ts must end with Z
    payload = {
        "message_id": "bad2",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:10:00",  # no Z
        "text": "bad ts",
    }

    res = post_webhook(client, payload)
    assert res.status_code == 422
