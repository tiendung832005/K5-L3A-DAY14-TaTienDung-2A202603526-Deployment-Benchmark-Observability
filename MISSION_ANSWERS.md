# MISSION ANSWERS — Day 14: Deployment, Benchmark & Observability

## Part 1 — Localhost vs Production

### 1. Kết quả chạy thử bản `develop`

```bash
curl -X POST "http://localhost:8000/ask?question=Hello"
```

```json
{
  "answer": "Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."
}
```

### 2. Các anti-pattern và cách khắc phục

1. **Hardcode secret trong mã nguồn.** `develop/app.py` (dòng 17–18) ghi cứng `OPENAI_API_KEY` và `DATABASE_URL`, khiến thông tin có thể bị lộ qua lịch sử Git. `production/app.py` (dòng 24) dùng `from config import settings` để đọc cấu hình từ biến môi trường.
2. **In secret ra log.** `develop/app.py` (dòng 33–38) dùng `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`, làm lộ khóa qua stdout và tạo log khó truy vấn. `production/app.py` (dòng 28–31 và 105–116) dùng log JSON có cấu trúc và chỉ ghi metadata như `question_length` và `client_ip`.
3. **Thiếu liveness và readiness probe.** Bản `develop` thiếu endpoint để nền tảng triển khai kiểm tra tiến trình và quyết định định tuyến. `production/app.py` (dòng 129–156) bổ sung `/health` và `/ready`, trong đó `/ready` trả về `503` khi ứng dụng chưa sẵn sàng.
4. **Cố định cấu hình mạng cho môi trường local.** `develop/app.py` (dòng 47–52) bind `localhost:8000` và bật `reload=True`. `production/app.py` (dòng 182–188) dùng `settings.host` (`0.0.0.0`), `settings.port` (đọc từ `PORT`) và `settings.debug` để điều khiển chế độ reload.
5. **Thiếu graceful shutdown.** Bản `develop` có thể ngắt request đang xử lý khi tiến trình dừng. `production/app.py` (dòng 40–66 và 171–179) quản lý vòng đời qua `lifespan`, chuyển `is_ready` sang `False` khi shutdown và đăng ký xử lý `SIGTERM`.

### 3. Bảng so sánh `develop` và `production`

| Tiêu chí            | `develop`                                                     | `production`                                            | Tầm quan trọng                                                          |
| ------------------- | ------------------------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------- |
| Secret và cấu hình  | Biến toàn cục ghi cứng như `OPENAI_API_KEY` và `DEBUG = True` | Đọc biến môi trường qua `config.settings`               | Giảm nguy cơ lộ secret và dùng cùng một bản build cho nhiều môi trường. |
| Logging             | `print()` có thể ghi cả secret                                | Log JSON có các trường `time`, `level`, `msg`           | Loki hoặc Datadog có thể lọc và tìm lỗi theo trường dữ liệu.            |
| Health và readiness | Thiếu probe                                                   | `/health` trả `200`, `/ready` trả `200` hoặc `503`      | Hỗ trợ restart ứng dụng bị treo và định tuyến đến instance sẵn sàng.    |
| Mạng và cổng        | `localhost:8000`, `reload=True`                               | `0.0.0.0`, cổng từ `PORT`, reload theo `settings.debug` | Cho phép Docker và nền tảng cloud chuyển traffic vào container.         |
| Vòng đời ứng dụng   | Có thể ngắt request khi dừng                                  | `lifespan` và xử lý `SIGTERM`                           | Cho request đang xử lý thời gian hoàn tất trước khi container dừng.     |

## Part 2 — Docker

### 1. Exercise 2.1 — Tối ưu Dockerfile và layer caching

1. **Multi-stage build giảm dung lượng ở đâu?** Stage `builder` dùng công cụ như `gcc` và `libpq-dev` để build các gói Python. Stage cuối dùng `python:3.11-slim` và chỉ copy các gói đã build cùng mã nguồn ứng dụng. Compiler, cache `pip` và file tạm nằm ngoài image cuối.
2. **Vì sao `COPY requirements.txt` đứng trước `COPY . .`?** Docker có thể tái sử dụng layer `RUN pip install` khi chỉ mã nguồn thay đổi và `requirements.txt` giữ nguyên.
3. **Vì sao chạy bằng `USER appuser`?** Chạy với quyền tối thiểu giúp giới hạn quyền của tiến trình trong container và giảm tác động khi ứng dụng bị khai thác.
4. **`.dockerignore` có tác dụng gì?** Loại `.git`, `__pycache__`, `.env`, `venv` và `reports` khỏi build context, giúp giảm dữ liệu gửi đến Docker daemon và tránh copy nhầm file nhạy cảm vào image.

### 2. So sánh kích thước image

```text
my-agent:advanced              9fdc6a8cd569        240MB         57.4MB
my-agent:develop               d283bebc773b       1.67GB          426MB
```

Image `my-agent:advanced` có kích thước **240 MB**, giảm **1.430 MB (85,6%)** so với `my-agent:develop` (**1,67 GB**), nhờ base image `python:3.11-slim` và multi-stage build.

### 3. Kết quả gọi thử container `my-agent:advanced`

```json
{
  "answer": "Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"
}
```

### 4. Exercise 2.4 — Kiến trúc và kết quả chạy Docker Compose

```text
Client → Nginx (80/443) → FastAPI Agent (8000)
                              ├─ Redis (6379)
                              └─ Qdrant (6333)
```

Nginx ánh xạ cổng `8088` và `8443` trên host tới cổng `80` và `443` trong container.

```text
NAME                       IMAGE                   COMMAND                  SERVICE   CREATED          STATUS                            PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   "uvicorn main:app --…"   agent     16 seconds ago   Up 4 seconds (health: starting)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            "/docker-entrypoint.…"   nginx     16 seconds ago   Up 4 seconds                      0.0.0.0:8088->80/tcp, [::]:8088->80/tcp, 0.0.0.0:8443->443/tcp, [::]:8443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    "./entrypoint.sh"        qdrant    16 seconds ago   Up 15 seconds (healthy)           6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          "docker-entrypoint.s…"   redis     16 seconds ago   Up 15 seconds (healthy)           6379/tcp
```

## Part 3 — Cloud Deployment

### 1. Thông tin deploy Agent Part 6

- **Nền tảng** Railway
- **URL public** `https://k5-l3a-day14-tatiendung-2a202603526.onrender.com`

### 2. So sánh `railway.toml` và `render.yaml`

| Tiêu chí                 | `railway.toml` (Railway)                                                                                                          | `render.yaml` (Render)                                                                                              |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Định dạng và cấu trúc    | TOML, cấu hình một service qua `[build]` và `[deploy]`.                                                                           | YAML, có thể khai báo nhiều service và database trong cùng file qua `services` và `databases`.                      |
| Build và chạy            | Có thể dùng Nixpacks hoặc chỉ định `dockerfilePath`, cùng các thiết lập `startCommand`, `healthcheckPath` và `restartPolicyType`. | Khai báo `runtime` (`docker` hoặc `python`), `dockerfilePath`, `buildCommand`, `startCommand` và `healthCheckPath`. |
| Biến môi trường và Redis | Tạo service Redis riêng trên dashboard và tham chiếu `${{Redis.REDIS_URL}}`.                                                      | Khai báo service Redis (`type: redis`) và dùng `fromService` để truyền `connectionString` vào `REDIS_URL`.          |

### 3. Exercise 3.3 — Pipeline CI/CD trên Google Cloud Run

Pipeline dựa trên `cloudbuild.yaml` và `service.yaml` trong `03-cloud-deployment/production-cloud-run/`.

1. **Build image.** Cloud Build dùng `gcr.io/cloud-builders/docker` để đóng gói mã nguồn và gắn tag `$COMMIT_SHA` và `latest`.
2. **Push image.** Đẩy image lên Google Container Registry hoặc Artifact Registry.
3. **Deploy lên Cloud Run.** Dùng `gcr.io/google.com/cloudsdktool/cloud-sdk` để chạy `gcloud run deploy`, cập nhật image, tài nguyên CPU/RAM, giới hạn auto-scaling (`minScale`/`maxScale`), biến môi trường và Secret Manager, rồi chuyển traffic sang revision mới.

## Part 4 — API Security

### 1. Kết quả kiểm thử Authentication và Rate Limit

Token xác thực đã được che.

**Không gửi token — `401 Unauthorized`**

```http
HTTP/1.1 401 Unauthorized

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

**Gửi token hợp lệ của tài khoản `student` — `200 OK`**

```http
HTTP/1.1 200 OK

{
  "question": "Hello",
  "answer": "Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.",
  "usage": {
    "requests_remaining": 9,
    "budget_remaining_usd": 1.6e-05
  }
}
```

**Vượt ngưỡng 10 request/phút — `429 Too Many Requests` ở request thứ 11**

```http
HTTP/1.1 429 Too Many Requests

{
  "detail": {
    "error": "Rate limit exceeded",
    "limit": 10,
    "window_seconds": 60,
    "retry_after_seconds": 59
  }
}
```

### 2. Cost Guard và Rate Limit

Trước mỗi lần gọi LLM, Cost Guard ước tính chi phí token đầu vào và đầu ra, rồi cộng với chi phí đã ghi trong Redis theo user hoặc API key và kỳ ngân sách ngày/tháng. Nếu `chi phí hiện tại + chi phí ước tính > ngân sách tối đa` (ví dụ `1 USD/ngày` cho `student`), API trả `402 Payment Required` trước khi gọi model.

- **Rate Limit** giới hạn số request trong một khoảng thời gian để giảm tải do request dồn dập.
- **Cost Guard** giới hạn chi phí theo token. Một request chứa prompt dài có thể nằm trong giới hạn số lượt gọi nhưng vẫn vượt ngân sách.

## Part 5 — Scaling & Reliability

### 1. Kết quả chạy `test_stateless.py` với `--scale agent=3`

```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: 6c64e7a1-fb78-490e-803d-27787e44ef7a

Request 1: [instance-cb9db5]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-98aef6]
  Q: Why do we need containers?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 3: [instance-4a2aff]
  Q: What is Kubernetes?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 4: [instance-cb9db5]
  Q: How does load balancing work?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 5: [instance-98aef6]
  Q: What is Redis used for?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-98aef6', 'instance-4a2aff', 'instance-cb9db5'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Kubernetes?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: How does load balancing work?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Redis used for?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...

✅ Session history preserved across all instances via Redis!
```

Nginx phân phối **5 request** trong cùng một session qua **3 instance**. Các instance dùng Redis làm nơi lưu lịch sử hội thoại chung, vì vậy kết quả vẫn có đủ **10 message**.

### 2. Phân biệt liveness probe và readiness probe

| Probe                | Kiểm tra                                                                           | Khi Redis mất kết nối                                                                                           |
| -------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Liveness (`/health`) | Tiến trình còn sống. Orchestrator có thể restart container khi probe thất bại.     | Vẫn trả `200 OK` nếu tiến trình ứng dụng còn sống.                                                              |
| Readiness (`/ready`) | Instance đã sẵn sàng nhận traffic, bao gồm kiểm tra dependency qua `redis.ping()`. | Trả `503 Service Unavailable` khi Redis lỗi hoặc ứng dụng đang shutdown để load balancer tạm ngừng gửi traffic. |

## Part 6 — Final Project

Kết quả chạy `check_production_ready.py`.

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

## AI Log

### CP0–CP2 — Thiết lập môi trường và lộ trình

- **Hỏi gì** Hỏi cách tóm tắt công việc trong ngày, thiết lập môi trường Linux hỗ trợ `SIGTERM` (`os.name == "posix"`) khi mạng nội bộ chặn cổng `80` làm `apt-get` và quá trình cài Ubuntu WSL2 gặp lỗi, và xử lý xung đột cổng `80`/`443` trong Docker Compose.
- **Nhận gì** Hướng dẫn build image `lab14-env` từ `python:3.11-slim` và `docker:cli` qua HTTPS, chuyển nguồn APT sang HTTPS trong Dockerfile và chạy `docker compose` trên PowerShell Windows.
- **Tự kiểm tra và thực hiện** Build `lab14-env`, xác minh `os.name == "posix"`, chạy kiểm thử Part 1 và đo kích thước image Part 2 (`1,67 GB` và `240 MB`).

### CP3–CP5 — API Security, Scaling và Final Project

- **Hỏi gì** Hỏi cách triển khai các TODO trong `06-lab-complete/`, gồm xác thực `X-API-Key`, rate limiter sliding window trên Redis, Cost Guard, log JSON, graceful shutdown qua `lifespan` và multi-stage Dockerfile.
- **Nhận gì** Mã nguồn triển khai các module trong `06-lab-complete/` và kịch bản kiểm thử tự động cho Part 4 và Part 5.
- **Tự kiểm tra và thực hiện** Chạy `test_stateless.py` với ba instance agent và `python check_production_ready.py`, đạt **12/12 tiêu chí** và **43/43 checks passed**.

## Part 7 — Benchmark & Observability

### 1. Tổng hợp kết quả Benchmark hiệu năng & chất lượng (`develop/`)
- **Load Test (`load_test.py`, Agent v2, 60 requests):**
  - Ở `concurrency=1`: Throughput đạt `4.75 req/s`, latency `p50=188.6ms`, `p95=217.5ms`, `p99=828.0ms`, `error_rate=1.67%` (đạt SLO `p95 <= 500ms` và `error_rate <= 2.0%`).
  - Khi tăng `concurrency=10`: Throughput tăng lên `26.37 req/s` (~5.5x so với `c=1`), `p95=376.3ms`, `p99=1704.8ms` (bắt đầu xuất hiện rõ tail latency do các request chậm bất thường).
  - Khi tăng `concurrency=20`: Throughput đạt `31.26 req/s`, `p50=191.9ms`, `p95=236.9ms`, `p99=1698.4ms`.
- **Thí nghiệm Tail Latency (`MOCK_SLOW_RATE` với 80 requests, `concurrency=10`):**
  - `MOCK_SLOW_RATE = 0.00`: `avg=187.3ms`, `p95=217.2ms`, `p99=223.7ms` (PASS SLO).
  - `MOCK_SLOW_RATE = 0.03`: `avg=228.3ms`, `p95=222.4ms`, `p99=1672.8ms` (PASS SLO `p95`, nhưng `p99` nhảy vọt gấp ~7.5 lần).
  - `MOCK_SLOW_RATE = 0.15`: `avg=433.0ms`, `p95=1707.7ms`, `p99=1714.1ms` (**FAIL SLO** `p95 <= 500ms` dù `avg` vẫn dưới 500ms).
- **Eval trên Golden Dataset (`eval/run_eval.py`, 23 câu hỏi):**
  - **Agent v1 (không retrieval):** Accuracy = `4.35%` (`1/23`), `avg_tokens=57.6`, `total_cost=$0.000411`, `cost/câu đúng=$0.00041115` → **FAIL** Quality Gate.
  - **Agent v2 (có retrieval, KB gốc):** Accuracy = `91.30%` (`21/23`), `avg_tokens=109.1`, `total_cost=$0.000762`, `cost/câu đúng=$0.00003627` → **PASS** Quality Gate (`>= 80%`), chỉ thiếu 2 câu `security-02` (JWT vs API key) và `scaling-03` (Kubernetes HPA).
  - **Agent v2 (sau khi bổ sung `KNOWLEDGE_BASE`):** Accuracy = **`100.0%` (`23/23`)**, `avg_tokens=113.9`, `total_cost=$0.000788`, `cost/câu đúng=$0.00003426`, `0` regression → **PASS** Quality Gate (`>= 85%`).

### 2. Kiến trúc Observability Stack & Alerting (`production/`)
- **Luồng thu thập dữ liệu giám sát (3 trụ cột Observability):**
  1. **Metrics (Prometheus `:9090` + Grafana `:3000`):** Các container `agent` expose endpoint `/metrics` (định dạng `prometheus_client` với `Counter`, `Gauge`, `Histogram`). Prometheus scrape định kỳ, đánh giá `alert_rules.yml` và cấp dữ liệu cho dashboard Golden Signals trên Grafana.
  2. **Traces (OpenTelemetry OTLP `:4318` → Jaeger `:16686`):** Mỗi request `/ask` tạo một root span kèm các child span (`retrieve_context`, `llm_generate`), giúp bóc tách chính xác thời gian từng bước và gắn event `exception` khi gọi LLM lỗi.
  3. **Logs (Structured JSON stdout):** Mọi dòng log đều xuất ra JSON chứa `request_id` và `trace_id` để đối chiếu trực tiếp từ biểu đồ latency/lỗi sang trace chi tiết trong Jaeger.
- **Báo cáo chi tiết:** Xem đầy đủ bảng số liệu, nhận xét và phân tích trong file [`BENCHMARK_REPORT.md`](BENCHMARK_REPORT.md).