# Lyftr.ai Backend Assignment—Webhook Ingestion API

A FastAPI-based webhook ingestion service that verifies HMAC signatures, stores messages in SQLite with idempotency, and exposes retrieval & analytics endpoints. Includes Docker Compose setup, structured JSON logs, and automated tests.
## Tech Stack
- **Python 3.11**
- **FastAPI**
- **SQLite**(persistent volume in Docker)
- **Pytest**(tests)
- **Docker+Docker Compose**
## Features
- **POST `/webhook`**
  - HMAC-SHA256 signature verification using `X-Signature`
  - Payload validation
  - Idempotent insert using `message_id` (exactly-once)
- **GET `/messages`**
  - Pagination: `limit`, `offset`
  - Filters: `from`, `since`, `q`
  - Deterministic ordering: `ts ASC, message_id ASC`
- **GET `/stats`**
  - Total messages,unique senders,top senders,first/last timestamps
- **Health checks**
  - `/health/live`
  - `/health/ready`
- **Metrics (Prometheus format)**
  - `/metrics`
- **Structured JSON logging**
  - One JSON log per request
  - Webhook logs include `message_id`, `dup`, `result`

---

🔌 API Endpoints
| Endpoint         | Method | Description                                                   |
|------------------|--------|---------------------------------------------------------------|
| `/health/live`   | GET    | Liveness: Returns `200 OK` if the service is running.         |
| `/health/ready`  | GET    | Readiness: Returns `200 OK` if the database is connected.     |
| `/webhook`       | POST   | Ingest: Accepts messages (Requires HMAC signature).           |
| `/messages`      | GET    | List: Retrieve messages with pagination and filtering.        |
| `/stats`         | GET    | Analytics: View real-time message statistics.                 |
| `/metrics`       | GET    | Returns counters and histograms for monitoring.                 


## Environment Variables
Create a `.env` file using `.env.example`.

Required:
- `WEBHOOK_SECRET`—Secret used to validate webhook HMAC signature
- `DATABASE_URL`—SQLite path

Example:
```env
WEBHOOK_SECRET=testsecret
DATABASE_URL=sqlite:////data/app.db
LOG_LEVEL=INFO


##  Design Decisions

###  HMAC Verification Implementation
We implemented security on the `/webhook` endpoint to ensure message authenticity.

* **Raw Payload Hashing:** We generate the signature using the **raw bytes** of the request body (`await request.body()`) rather than the parsed JSON. This avoids discrepancies caused by whitespace or serialization differences.
* **Algorithm:** We utilize the standard **SHA-256** algorithm via Python's built-in `hashlib` library.
* **Timing Attack Prevention:** To verify the signature, we use `hmac.compare_digest(computed, received)`.
    * This function performs a **constant-time comparison**, ensuring that the time taken to reject a fake signature does not leak information about the secret key (mitigating timing attacks).
* **Validation Order:** Signature verification is performed **before** JSON parsing or database connection. This ensures invalid requests are rejected immediately (401 Unauthorized), saving server resources.


### Pagination Strategy
To handle potentially large datasets efficiently, we implemented a standard **Offset-Based Pagination** contract on the `/messages` endpoint.

* **Parameters:**
    * `limit`: Controls the page size (Default: 50). We strictly enforce a **maximum of 100** items per request to prevent database performance degradation from unconstrained queries.
    * `offset`: Specifies the number of records to skip (Default: 0).
* **Envelope Response Pattern:**
    * We chose not to return a raw JSON array. Instead, we wrap the results in a structured object containing both the `data` and pagination `metadata` (`total`, `limit`, `offset`).
    * **Benefit:** This allows the frontend client to easily calculate total pages and build UI pagination controls (e.g., "Page 1 of 10") without needing a separate API call.


###  Analytics & Aggregation Strategy
For the `/stats` endpoint, we prioritized performance and memory efficiency by leveraging **Database-Side Aggregation** instead of processing data in the application layer.

* **SQL-Level Computation:**
    * Instead of fetching all message records into Python memory (which is O(N) and memory-intensive), we utilized SQLAlchemy's `func.count()`, `func.min()`, and `func.max()` to perform calculations directly within the database engine.
* **Efficient Grouping:**
    * The "Messages per Sender" breakdown is generated using a single SQL `GROUP BY` query. This allows the database to sort and aggregate thousands of records instantly, returning only the summary results to the API.
* **Distinct Counting:**
    * To accurately calculate the `senders_count`, we utilized `func.count(distinct(Message.from_msisdn))`. This ensures that multiple messages from the same phone number do not inflate the active user count.

###  Prometheus Metrics (Observability)
To support production monitoring, the service exposes real-time metrics in the standard Prometheus exposition format.


####  Key Metrics Tracked
* **`http_requests_total`**: A counter tracking all incoming HTTP requests, labeled by `path` and `status` (e.g., 200, 401, 422).
* **`webhook_requests_total`**: A specific counter for webhook processing outcomes, labeled by `result` (e.g., `created`, `duplicate`, `invalid_signature`, `validation_error`).
* **`request_latency_ms`**: A histogram measuring request duration with predefined buckets for performance analysis.
