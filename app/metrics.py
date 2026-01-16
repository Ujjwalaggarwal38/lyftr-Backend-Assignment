from collections import defaultdict
from threading import Lock

_lock = Lock()

# Counters
_http_requests_total = defaultdict(int)   # key: (path, status)
_webhook_requests_total = defaultdict(int)  # key: result


def inc_http(path: str, status: int):
    with _lock:
        _http_requests_total[(path, str(status))] += 1


def inc_webhook(result: str):
    with _lock:
        _webhook_requests_total[(result,)] += 1


def render_prometheus() -> str:
    lines = []

    # http_requests_total
    lines.append("# TYPE http_requests_total counter")
    with _lock:
        for (path, status), count in _http_requests_total.items():
            lines.append(f'http_requests_total{{path="{path}",status="{status}"}} {count}')

        # webhook_requests_total
        lines.append("# TYPE webhook_requests_total counter")
        for (result,), count in _webhook_requests_total.items():
            lines.append(f'webhook_requests_total{{result="{result}"}} {count}')

    return "\n".join(lines) + "\n"
