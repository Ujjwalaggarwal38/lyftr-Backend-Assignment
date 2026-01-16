from fastapi import FastAPI, Request, Header, HTTPException,Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import re
import hmac
import hashlib

from .models import init_db
from .config import WEBHOOK_SECRET,LOG_LEVEL
from .storage import insert_message, fetch_messages, count_messages, get_stats
from .logging_utils import JsonLogger, create_request_id, RequestTimer
from fastapi.responses import PlainTextResponse
from .metrics import inc_http, inc_webhook, render_prometheus


E164_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")

class WebhookMessage(BaseModel):
    message_id: str = Field(..., min_length=1)
    from_: str = Field(..., alias="from")
    to: str
    ts: str
    text: Optional[str] = Field(default=None, max_length=4096)

    def validate_fields(self):
        if not E164_REGEX.match(self.from_):
            raise ValueError("Invalid from number")
        if not E164_REGEX.match(self.to):
            raise ValueError("Invalid to number")

        if not self.ts.endswith("Z"):
            raise ValueError("ts must end with Z")

        try:
            datetime.fromisoformat(self.ts.replace("Z", "+00:00"))
        except Exception:
            raise ValueError("Invalid ts format")

def compute_signature(secret: str, raw_body: bytes) -> str:
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()


app = FastAPI(title="Lyftr Webhook API")
logger = JsonLogger(level=LOG_LEVEL)

@app.middleware("http")
async def json_logging_middleware(request: Request, call_next):
    request_id = create_request_id()
    timer = RequestTimer()

    # store request_id (useful later)
    request.state.request_id = request_id

    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        inc_http(request.url.path, status_code)

        return response
    finally:
        latency_ms = timer.ms()

        log_payload = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": status_code,
            "latency_ms": latency_ms,
        }

        # base request logs
        logger.log("INFO", log_payload)





@app.on_event("startup")
def on_startup():
    init_db()
    if WEBHOOK_SECRET == "":
        print("WARNING: WEBHOOK_SECRET not set. /health/ready will return 503.")

@app.get("/health/live")
def live():
    return {"status": "live"}

@app.get("/health/ready")
def ready():
    if WEBHOOK_SECRET == "":
        return JSONResponse(status_code=503, content={"status": "not-ready"})
    return {"status": "ready"}

@app.post("/webhook")
async def webhook(
    request: Request,
    x_signature: str = Header(default="", alias="X-Signature")
):
    timer = RequestTimer()

    result = "unknown"
    dup = False
    message_id = None
    status = 200

    try:
        if WEBHOOK_SECRET == "":
            status = 503
            result = "secret_missing"
            raise HTTPException(status_code=503, detail="webhook secret not configured")

        raw_body = await request.body()

        expected_sig = compute_signature(WEBHOOK_SECRET, raw_body)

        if not x_signature or x_signature != expected_sig:
            status = 401
            result = "invalid_signature"
            raise HTTPException(status_code=401, detail="invalid signature")

        try:
            payload = await request.json()
        except Exception:
            status = 422
            result = "validation_error"
            raise HTTPException(status_code=422, detail="invalid json")

        message_id = payload.get("message_id")

        try:
            msg = WebhookMessage(**payload)
            msg.validate_fields()
        except Exception as e:
            status = 422
            result = "validation_error"
            raise HTTPException(status_code=422, detail=str(e))

        created, duplicate = insert_message(
            message_id=msg.message_id,
            from_msisdn=msg.from_,
            to_msisdn=msg.to,
            ts=msg.ts,
            text=msg.text
        )

        dup = duplicate
        result = "duplicate" if duplicate else "created"

        status = 200
        return {"status": "ok"}

    finally:
        inc_webhook(result)
        logger.log("INFO", {
            "request_id": getattr(request.state, "request_id", None),
            "method": "POST",
            "path": "/webhook",
            "status": status,
            "latency_ms": timer.ms(),
            "message_id": message_id,
            "dup": dup,
            "result": result
        })

@app.get("/messages")
def get_messages(
    limit: int = 50,
    offset: int = 0,
    from_msisdn: Optional[str] = Query(default=None, alias="from"),
    since: Optional[str] = None,
    q: Optional[str] = None
):
    # limit/offset validation (assignment rules)
    if limit < 1:
        raise HTTPException(status_code=422, detail="limit must be >= 1")
    if limit > 100:
        raise HTTPException(status_code=422, detail="limit must be <= 100")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be >= 0")

    # ✅ Normalization for "from" query param
    # If caller uses /messages?from=+9198..., the "+" becomes space in query parsing.
    if from_msisdn:
        from_msisdn = from_msisdn.strip()
        # if starts with digits (or accidental space), add '+'
        if from_msisdn and not from_msisdn.startswith("+") and from_msisdn[0].isdigit():
            from_msisdn = "+" + from_msisdn

    total = count_messages(from_msisdn, since, q)
    data = fetch_messages(from_msisdn, since, q, limit, offset)

    return {
        "data": data,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.get("/stats")
def stats():
    return get_stats()

@app.get("/metrics")
def metrics():
    text = render_prometheus()
    return PlainTextResponse(content=text, media_type="text/plain")




