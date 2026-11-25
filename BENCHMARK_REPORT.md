# Benchmark & Observability Report — Day 14

- **Họ tên** Tạ Tiến Dũng (2A202603526 — K5-L3A)
- **Ngày chạy** 25/11/2026
- **Môi trường** Windows 11, Docker Desktop (WSL2 backend, 4 CPU / 8GB RAM), Python 3.11

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Đảm bảo trải nghiệm phản hồi gần như tức thì cho người dùng cuối (95% request hoàn thành dưới 0.5 giây, bao gồm cả bước retrieval ~20ms và sinh câu trả lời ~150–200ms). |
| Error rate `/ask` | < 2.0 % | Cho phép sai số nhỏ từ lỗi upstream ngẫu nhiên (`MOCK_ERROR_RATE=1%`) nhưng vẫn duy trì độ khả dụng > 98% và cảnh báo sớm khi nhà cung cấp LLM gặp sự cố. |
| Accuracy trên golden dataset | ≥ 85.0 % | Đảm bảo agent trả lời chính xác phần lớn các câu hỏi kỹ thuật cốt lõi trong knowledge base và ngăn chặn regression trước mỗi lần deploy. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.75 | 188.6 | 217.5 | 828.0 | 1.67% | PASS |
| 5 | 23.27 | 180.9 | 214.8 | 829.7 | 1.67% | PASS |
| 10 | 26.37 | 188.7 | 376.3 | 1704.8 | 1.67% | PASS |
| 20 | 31.26 | 191.9 | 236.9 | 1698.4 | 0.00% | PASS |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- RPS **không tăng tuyến tính** khi concurrency tiếp tục tăng cao: từ `c=1` lên `c=5`, RPS tăng gần 4.9 lần (`4.75` → `23.27 req/s`), nhưng từ `c=5` lên `c=10` chỉ tăng thêm ~13% (`26.37 req/s`) và lên `c=20` đạt `31.26 req/s`.
- Nguyên nhân vì khi nhiều request xử lý đồng thời trên 1 worker Uvicorn, event loop và CPU phải chia sẻ tài nguyên chuyển đổi ngữ cảnh (context switching), đồng thời các request rơi vào nhánh chậm (`MOCK_SLOW_MS = 1500ms`) kéo dài tổng thời gian chạy của cả batch và làm tăng mạnh tail latency (`p99` lên ~`1700ms`).

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 187.3 | 217.2 | 223.7 |
| 0.03 (mặc định) | 228.3 | 222.4 | 1672.8 |
| 0.15 | 433.0 | 1707.7 | 1714.1 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- Chỉ số nhạy nhất với request chậm là **`p99`** (biến động ngay từ khi `MOCK_SLOW_RATE = 0.03`, tăng vọt từ `223.7ms` lên `1672.8ms`), tiếp theo là **`p95`** (vượt ngưỡng `1707.7ms` khi tỷ lệ request chậm vượt quá 5%).
- SLO **không nên đặt theo average** vì giá trị trung bình bị kéo xuống bởi 85%–97% request nhanh: ngay cả khi có tới 15% người dùng phải chờ hơn 1.7 giây (`p95 = 1707.7ms`, vi phạm SLO 500ms), `avg` vẫn chỉ ở mức `433.0ms` và che giấu hoàn toàn trải nghiệm tệ của nhóm người dùng bị chậm.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.6 | 109.1 | 113.9 |
| Tổng cost (USD) | $0.000411 | $0.000762 | $0.000788 |
| Cost / câu đúng (USD) | $0.00041115 | $0.00003627 | $0.00003426 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Bổ sung entry về cơ chế xác thực JWT (có chữ ký số và thời gian hết hạn) so với API key cố định vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Bổ sung entry giải thích cơ chế tự động scale pod của Kubernetes HPA dựa trên CPU, memory và custom metrics vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Về chất lượng:** Agent v2 (có bước retrieval context từ Knowledge Base) giúp tăng độ chính xác vượt bậc từ `4.35%` (`1/23`) lên `91.30%` và đạt `100.0%` (`23/23`) sau khi bổ sung đủ tài liệu, trong khi v1 chỉ trả lời được câu chung chung.
- **Về chi phí & latency:** Vì v2 phải chèn thêm ngữ cảnh tìm được vào prompt nên `avg_tokens` tăng gần gấp đôi (`57.6` → `113.9` tokens/câu) và `p95 latency` tăng nhẹ ~`21ms` (`185.0ms` → `206.3ms` do bước retrieval). Tuy nhiên, xét trên hiệu quả thực tế, **chi phí trên mỗi câu trả lời đúng (`cost / câu đúng`) của v2 giảm tới ~12 lần** so với v1 (`$0.00003426` so với `$0.00041115`).

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals: Request Rate, Error Rate, Latency p95/p99, Token/Cost)
- [x] Một trace chậm trong Jaeger (thấy span `llm_generate` chiếm > 95% tổng thời gian)
- [x] Một trace lỗi trong Jaeger (có event `exception` với `LLMError: Upstream LLM error: 503 Service Unavailable`)
- [x] Trang Alerts của Prometheus với alert `HighErrorRate` / `HighLatencyP95` đang ở trạng thái **FIRING**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `HighErrorRate` (tỷ lệ HTTP 5xx > 5%) | ~30–45 giây (15s scrape + 15s `for` duration) | Panel **Error Rate (%)** & **HTTP Status Codes (5xx)** trên Grafana |
| B | `MOCK_SLOW_RATE=0.3` | `HighLatencyP95` (`p95 > 500ms`) | ~45–60 giây | Panel **Latency Percentiles (p50 / p95 / p99)** trên Grafana |
| C | `LLM_MODEL=mock-llm-large` | `HighLatencyP95` / `HighHourlyCost` (do hệ số latency 2.5x và giá token cao hơn ~16x) | ~60 giây | Panel **Estimated Cost / Hour ($)** & **Latency Percentiles** |
| D | `docker pause` 1 instance | `InstanceDown` (`up == 0` khi Prometheus không scrape được instance bị pause) | ~30–45 giây | Panel **Active Instances (`up`)** & **Throughput per Instance** |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | Không firing | Hệ thống vẫn trả về HTTP 200 nhanh nhưng chất lượng nội dung giảm sút |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

- Vì các metric hạ tầng (HTTP 200, latency thấp, CPU/RAM bình thường) không đo được độ đúng ngữ nghĩa của câu trả lời AI, cần kết hợp 3 lớp kiểm soát:
  1. **CI/CD Quality Gate bắt buộc:** Chạy tự động `eval/run_eval.py` trên golden dataset trước khi deploy; chặn release ngay nếu accuracy giảm so với baseline (regression).
  2. **Online Evaluation / Sampling LLM-as-a-Judge:** Lấy mẫu ngẫu nhiên 5–10% traffic production gửi bất đồng bộ qua mô hình chấm điểm hoặc kiểm tra độ liên quan giữa câu trả lời và context retrieved, xuất metric `agent_eval_score` sang Prometheus để đặt alert.
  3. **Theo dõi tín hiệu phản hồi người dùng & Business Metrics:** Gắn nút thumbs-up/thumbs-down trên giao diện, theo dõi tỷ lệ người dùng hỏi lại cùng một chủ đề hoặc tỷ lệ không tìm thấy context (`retrieval_empty_rate`).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất ghi nhận được trong quá trình chạy tải:

- `trace_id`: `4f8a9c2e1b7d3056a12e4f89c0d3b712`
- Tổng thời gian: `1719.4 ms`
- Span chiếm nhiều thời gian nhất: `llm_generate` (`1695.2 ms`, chiếm `98.6%` tổng thời gian xử lý)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T10:14:22.418Z", "level": "INFO", "event": "ask_completed", "request_id": "req-89f21a", "trace_id": "4f8a9c2e1b7d3056a12e4f89c0d3b712", "agent_version": "v2", "model": "mock-llm-small", "status": 200, "latency_ms": 1719.4, "input_tokens": 112, "output_tokens": 38, "cost_usd": 0.0000396}
```

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 31.4 | 215.0 | 1720.0 | 1785.0 | 1.12% |
| 3 | 78.6 | 189.0 | 345.0 | 1695.0 | 0.98% |

### 5.1 Ảnh hưởng của scaling lên p95

Khi scale từ 1 lên 3 container agent phía sau Nginx Load Balancer, thông lượng tăng khoảng **2,5 lần** (từ 31.4 lên 78.6 RPS). p95 giảm từ **1720.0 ms** xuống **345.0 ms**, đạt lại SLO dưới 500 ms.

### 5.2 Nút thắt hiệu năng

- **Một instance.** Với giới hạn 0,5 CPU và 256 MB RAM, 100 người dùng đồng thời tạo hàng đợi tại worker. Thời gian chờ CPU và event loop đẩy p95 lên hơn 1,7 giây.
- **Ba instance.** Nginx phân phối tải theo round-robin, giảm thời gian xếp hàng ở tầng ứng dụng. Các request đi vào nhánh chậm của upstream LLM (`MOCK_SLOW_RATE`) vẫn mất khoảng 1,5 giây, khiến p99 còn khoảng 1695 ms. Timeout, retry hoặc caching ở tầng LLM là các hướng xử lý được đề xuất.

## 6. Kết luận

### 6.1 Ba điều học được về benchmark và observability

1. **Theo dõi p95 và p99 để thấy tail latency.** Độ trễ trung bình có thể vẫn dưới ngưỡng khi một nhóm người dùng phải chờ lâu vì tải cao hoặc upstream phản hồi chậm.
2. **Chạy Eval Quality Gate trước khi deploy thay đổi prompt, model hoặc Knowledge Base.** Chuyển về agent v1 hoặc sửa nhầm keyword có thể làm giảm độ chính xác ngay cả khi HTTP 5xx và mức sử dụng CPU vẫn ổn định.
3. **Liên kết log, metric và trace bằng `request_id` và `trace_id`.** Metric và cảnh báo Prometheus giúp phát hiện thời điểm bất thường. Trace và log JSON giúp xác định bước gây chậm, chẳng hạn retrieval hoặc `llm_generate`.

### 6.2 Metric và alert cần bổ sung khi triển khai production

- **Chất lượng trực tuyến.** Theo dõi `agent_retrieval_hit_rate` và `agent_eval_quality_score`. Tỷ lệ tìm thấy tài liệu liên quan giảm đột ngột có thể báo hiệu lỗi vector DB hoặc dữ liệu mới chưa được index.
- **Hiệu quả sử dụng token và tốc độ tiêu ngân sách.** Theo dõi `llm_budget_burn_rate_usd_per_hour` để cảnh báo khi chi phí tăng nhanh hơn dự kiến.
- **Timeout và fallback của upstream LLM.** Theo dõi `llm_upstream_timeout_total` cùng tỷ lệ gọi model dự phòng khi provider chính phản hồi chậm.
