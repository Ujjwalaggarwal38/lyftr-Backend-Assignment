import json
import logging
import time
import uuid
from datetime import datetime, timezone
from fastapi import Request


def iso_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class JsonLogger:
    def __init__(self,level:str="INFO"):
        self.logger = logging.getLogger("lyftr")
        self.logger.setLevel(level)
        self.logger.handlers = []  # avoid duplicate handlers
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)

    def log(self, level: str, payload: dict):
        payload.setdefault("ts", iso_now())
        payload.setdefault("level", level)
        line = json.dumps(payload, ensure_ascii=False)
        if level == "ERROR":
            self.logger.error(line)
        elif level == "WARNING":
            self.logger.warning(line)
        else:
            self.logger.info(line)


def create_request_id() -> str:
    return str(uuid.uuid4())


class RequestTimer:
    def __init__(self):
        self.start = time.perf_counter()

    def ms(self) -> int:
        return int((time.perf_counter() - self.start) * 1000)
