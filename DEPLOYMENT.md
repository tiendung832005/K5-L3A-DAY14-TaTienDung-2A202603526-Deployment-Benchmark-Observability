# Deployment — Day 14: Production AI Agent

## 1. Thông tin Deployment
- **Nền tảng Cloud:** Render (`Web Service` + `Key Value / Redis`)
- **Public URL:** `https://k5-l3a-day14-tatiendung-2a202603526.onrender.com`
- **Thư mục nguồn deploy:** `06-lab-complete/` (build bằng multi-stage `Dockerfile`)
- **Trạng thái:** Live & Healthy (`/health` → 200, `/ready` → 200)

## 2. Biến môi trường đã cấu hình trên Render
*(Không ghi giá trị secret thật vào file này)*

| Biến môi trường | Mô tả & Cấu hình |
| :--- | :--- |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | Khóa bí mật xác thực header `X-API-Key` (cấu hình trên Render Environment) |
| `REDIS_URL` | Internal Key Value URL kết nối tới instance Redis trên Render (`redis://...`) |
| `RATE_LIMIT_PER_MINUTE` | `20` |
| `DAILY_BUDGET_USD` | `5.0` |

## 3. Lệnh tự kiểm tra Endpoint Public
```bash
BASE="[https://k5-l3a-day14-tatiendung-2a202603526.onrender.com](https://k5-l3a-day14-tatiendung-2a202603526.onrender.com)"

# 1. Liveness probe -> 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness probe (kiểm tra kết nối Redis) -> 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. Gọi /ask thiếu API Key -> 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'

# 4. Gọi /ask kèm X-API-Key hợp lệ -> 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'