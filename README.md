# Free LLM Provider Discovery

[![CI](https://github.com/nguyenson/app-free-api-information-retrieval/actions/workflows/ci.yml/badge.svg)](https://github.com/nguyenson/app-free-api-information-retrieval/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230)](https://github.com/astral-sh/ruff)
[![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen)](#phát-triển-enterprise)

CLI tool để **khám phá, kiểm tra và tổng hợp** danh sách các nhà cung cấp API LLM miễn phí.

## ⚠️ Ứng dụng hoạt động thế nào?

Tool này **KHÔNG quét toàn bộ internet** (điều đó là bất khả thi). Nó hoạt động theo
cách giống mọi công cụ cùng loại:

1. **Registry curate thủ công** — danh sách provider được maintain trong code
   (`src/discovery/providers_part1.py`, `providers_part2.py`), lấy từ:
   - Tài liệu chính thức của từng provider
   - GitHub awesome-lists (free-llm-apis, ...)
   - Cộng đồng AI

2. **Verification tự động** — ping nhẹ tới `{base_url}/models` của từng provider
   để xác nhận endpoint còn hoạt động (không spam, có timeout).

3. **Aggregation** — gom kết quả thành JSON/YAML, lọc chỉ model miễn phí.

## Cài đặt

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Docker

Image: `free-llm-provider-discovery:latest` (multi-stage build, non-root user,
HEALTHCHECK chạy lệnh `health` của chính CLI).

### Build & chạy lệnh một-shot

Mọi lệnh CLI đều chạy được qua `docker compose run app <lệnh>` — arguments
được truyền xuyên vào `ENTRYPOINT ["python", "run.py"]`:

```bash
# Build image
docker compose build

# Liệt kê tất cả provider
docker compose run app list

# Liệt kê + kiểm tra endpoint còn sống
docker compose run app list --verify

# Lọc theo tag
docker compose run app list --tag free-tier

# Chỉ provider không cần API key, xuất CSV
docker compose run app list --no-auth --format csv

# Kiểm tra 1 provider cụ thể
docker compose run app check --provider groq

# Cập nhật & lưu ra file JSON (volumes mount ./data → /app/data)
docker compose run app update --output data/providers.json

# Health check
docker compose run app health

# AI discovery (cần .env chứa AI_API_KEY)
docker compose run app discover-ai --verify

# Live discovery (OpenRouter, không cần key)
docker compose run app discover-live --output data/live_free.json

# Deep Web Search
docker compose run app discover-web --keywords "free llm api"

# Xem help
docker compose run app --help
docker compose run app list --help
```

> Kết quả `--output` lưu vào `./data` trên host nhờ volume mount
> (`./data:/app/data`). Command mặc định của service `app` là `list`,
> nên `docker compose run app` (không args) cũng chạy được.

### REST API server (lâu dài)

```bash
docker compose up api          # serve --host 0.0.0.0 --port 8000
docker compose logs -f api     # xem log
docker compose down api        # dừng
```

- API: `http://localhost:8000` — Swagger UI: `http://localhost:8000/docs`
- `restart: unless-stopped` — tự khởi động lại khi Docker host reboot.

Chạy bằng `docker run` thuần (không compose):

```bash
docker build -t free-llm-provider-discovery .
docker run --rm --env-file .env -v $(pwd)/data:/app/data free-llm-provider-discovery list --verify
docker run --rm -p 8000:8000 --env-file .env free-llm-provider-discovery serve --host 0.0.0.0 --port 8000
```

### Yêu cầu `.env`

`docker-compose.yml` dùng `env_file: .env` — file phải tồn tại trước khi
chạy `docker compose up` / `run`. Nếu chưa có:

```bash
cp .env.example .env
```

### Healthcheck trong container

Docker tự ping health:

```bash
docker inspect --format='{{json .State.Health}}' free-llm-provider-discovery_api
docker inspect free-llm-provider-discovery_api | grep -A 10 '"Health"'
```

## Sử dụng

```bash
# Liệt kê tất cả provider
./venv/bin/python run.py list

# Liệt kê + kiểm tra endpoint còn sống
./venv/bin/python run.py list --verify

# Lọc theo tag (free-tier, openai-compatible, china, ...)
./venv/bin/python run.py list --tag free-tier

# Chỉ hiện provider không cần API key
./venv/bin/python run.py list --no-auth

# Kiểm tra 1 provider cụ thể
./venv/bin/python run.py check --provider groq

# Cập nhật & lưu ra file JSON
./venv/bin/python run.py update --output data/providers.json

# Xuất YAML
./venv/bin/python run.py update --output data/providers.yaml

# Xuất CSV (mở được bằng Excel / Google Sheets)
./venv/bin/python run.py list --format csv
./venv/bin/python run.py list --output data/providers.csv

# Kiểm tra nhanh health
./venv/bin/python run.py health
./venv/bin/python run.py health --output health.json

# Chạy REST API server
./venv/bin/python run.py serve --port 8000

# Bật debug logging
./venv/bin/python run.py list --verbose
```

## 🤖 AI Discovery (tìm provider bằng AI)

Ứng dụng có chế độ dùng AI để tự động tìm provider miễn phí mới.

**1. Cấu hình** — copy `.env.example` → `.env` và điền:

```bash
cp .env.example .env
```

```env
AI_PROVIDER_BASE_URL=https://openrouter.ai/api/v1   # endpoint OpenAI-compatible
AI_API_KEY=sk-or-v1-xxxx                            # API key của bạn
AI_MODEL=openai/gpt-4o-mini                         # model rẻ là đủ
AI_TIMEOUT=60
```

> AI provider có thể là bất kỳ endpoint OpenAI-compatible nào: OpenRouter,
> Groq, Gemini, Mistral, DeepSeek, local Ollama (`http://localhost:11434/v1`), ...

**2. Chạy AI discovery:**

```bash
# Tìm provider mới bằng AI
./venv/bin/python run.py discover-ai

# Tìm + verify endpoint + lưu ra file
./venv/bin/python run.py discover-ai --verify --output data/ai_providers.json
```

AI sẽ trả về JSON đúng schema Provider, tự động được parse vào pipeline
verification/aggregation hiện có. Provider tìm bởi AI được tag `ai-discovered`.

> ⚠️ **Lưu ý**: `discover-ai` dựa vào trí nhớ của LLM (training data), KHÔNG
> truy cập internet thật. Kết quả cần verify. Muốn dữ liệu internet thật →
> dùng `discover-live` bên dưới.

## 🌐 Live Discovery (dữ liệu internet THẬT)

Lệnh `discover-live` query trực tiếp **OpenRouter `/models` API** (public,
không cần API key) và lọc model có pricing thật = $0. Đây là dữ liệu
**trạng thái thực tế tại thời điểm gọi** — không phải trí nhớ LLM hay
registry cứng:

```bash
# Tìm model free thật từ internet (không cần API key, không cần .env)
./venv/bin/python run.py discover-live

# Lưu snapshot hiện tại ra file
./venv/bin/python run.py discover-live --output data/live_free.json

# Hiển thị tất cả model free tìm thấy
./venv/bin/python run.py discover-live --show-all-models
```

So sánh 4 chế độ discovery:

| Chế độ | Nguồn dữ liệu | Cần key | Độ tươi |
|---|---|---|---|
| `list` | Registry cứng trong code (22 providers) | ❌ | Cũ nhất (theo lần curate) |
| `discover-ai` | Trí nhớ của LLM | ✅ (AI key) | Cũ (training data) |
| `discover-live` | **OpenRouter API trực tiếp** | ❌ | **Mới nhất** ✅ |
| `discover-web` | **5 nguồn internet thật** (Reddit/HN/DDG/GitHub/LMSpeed) | ❌ | **Mới nhất** ✅ |

### Nguồn 'shared' — API key cộng đồng (bansos)

`discover-web --sources shared` query trực tiếp các trang chia sẻ key cộng đồng:
- **Crown AI status API** (`crown.ai.id/api/status`, JSON public) — pool sống/chết,
  model nào online hiện tại
- **LMSpeed shared keys** (`lmspeed.net/free-api-keys`) — baseUrl thật của key
  cộng đồng đang chia sẻ (Nightrouter, Agentrouter, ...)

Registry cũng có sẵn 2 community pool Indonesia: **Crown AI** (`crown.ai.id/v1`,
key miễn phí tại `/bansos`) và **free.ai.id** (không cần đăng ký).

## 📤 Xuất CSV cho spreadsheet

`--format csv` hoặc file `--output *.csv` — mỗi (provider, model) là 1 row,
mở trực tiếp bằng Excel / Google Sheets:

```bash
# In CSV ra stdout
./venv/bin/python run.py list --format csv

# Lưu ra file (cột: provider, base_url, status, auth_required, api_style,
# tags, model_id, model_name, is_free, context_length, supports_streaming,
# rate_limit, last_updated)
./venv/bin/python run.py list --output data/providers.csv

# Hoặc kết hợp với --verify / --tag
./venv/bin/python run.py list --verify --output data/providers.csv
```

## 🔔 Webhook notification khi provider đổi status

Sau khi verify (`list --verify`, `update`), tool so sánh status registry với
kết quả verify. Nếu có provider đổi status (ví dụ `active` → `inactive`), tool
POST payload JSON tới `WEBHOOK_URL`:

```env
# .env
WEBHOOK_URL=https://hooks.slack.com/services/xxx    # trống = tắt thông báo
WEBHOOK_TIMEOUT=10
WEBHOOK_ENABLED=true
```

Payload mẫu:

```json
{
  "event": "provider_status_changed",
  "version": "1.4.0",
  "timestamp": "2026-10-28T00:00:00+00:00",
  "total_changes": 1,
  "changes": [
    {"provider": "Groq", "base_url": "https://api.groq.com/openai/v1",
     "old_status": "active", "new_status": "inactive"}
  ]
}
```

> Webhook fire-and-forget an toàn: lỗi network không bao giờ làm crash pipeline
> verify. Nếu chưa cấu hình `WEBHOOK_URL`, CLI vẫn in ra số provider đổi status.

## 🌐 REST API (query từ app khác)

Chạy API server (FastAPI + uvicorn):

```bash
./venv/bin/python run.py serve --host 0.0.0.0 --port 8000
# Swagger UI: http://localhost:8000/docs
```

Endpoints:

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/v1/providers?tag=free-tier&no_auth=false&free_only=true` | Danh sách provider, hỗ trợ lọc |
| GET | `/api/v1/providers/{name}` | Chi tiết 1 provider (404 nếu không có) |
| GET | `/api/v1/health` | Health report (registry + config) |
| GET | `/api/v1/version` | Version API |

Ví dụ:

```bash
curl http://localhost:8000/api/v1/providers?tag=free-tier
curl http://localhost:8000/api/v1/providers/groq
```

Hoặc dùng Docker (xem section [Docker](#docker)):

```bash
docker compose up api   # API chạy tại http://localhost:8000
```

## Kiến trúc (Architecture)

```
┌─────────────────────────────────────────────────────────────────┐
│                           CLI (Click + Rich)                     │
│  list · check · update · discover-ai · discover-live · health    │
│  serve (REST API)                                                │
└───────┬──────────────┬──────────────┬──────────────────┬────────┘
        │              │              │                  │
        ▼              ▼              ▼                  ▼
┌──────────────┐ ┌───────────┐ ┌─────────────┐ ┌────────────────┐
│  DISCOVERY   │ │VERIFICATION│ │AGGREGATION  │ │   OUTPUT       │
│              │ │            │ │             │ │                │
│ • Registry   │→│ Async      │→│ ProviderList│→│ JSON / YAML    │
│   (curate)   │ │ checker    │ │ ProviderList│ │ CSV            │
│   20 curated │ │ semaphore 5│ │ filter free │ │ console table  │
│   providers  │ │ retry 429/ │ │ version     │ │ file output    │
│              │ │ backoff    │ │             │ │ progress bar   │
│ • AI Agent   │ │ + progress │ │             │ │                │
│   (LLM-based)│ │   callback │ │             │ │                │
│ • Live       │ │            │ │             │ │                │
│   (OpenRouter│ │  Webhook   │ │             │ │                │
│    API thật) │ │  notify on │ │             │ │                │
│              │ │  status    │ │             │ │                │
│              │ │  change    │ │             │ │                │
└──────────────┘ └───────────┘ └─────────────┘ └────────────────┘
        │                                            │
        └────────────── src/models.py ────────────────┘
              (Pydantic: Provider, Model, ProviderList)
```

**Data flow:**
1. `discovery/` sinh ra list `Provider` (registry cứng, AI, hoặc live API)
2. `verification/checker.py` ping song song (semaphore 5, retry 429/5xx) → status ACTIVE/INACTIVE/RATE_LIMITED
3. `aggregation/aggregator.py` gom thành `ProviderList` (version + timestamp)
4. Xuất JSON/YAML, chỉ giữ model free (`only_free=True` default)

## Cấu trúc project

```
src/
├── models.py                    # Data models (Provider, Model, ...)
├── config.py                    # Load .env (AI_*, WEBHOOK_*)
├── logging_config.py            # Structured logging (stdlib)
├── discovery/
│   ├── __init__.py              # Gộp registry + helpers
│   ├── providers_part1.py       # Providers phổ biến (OpenRouter, Groq, ...)
│   ├── providers_part2.py       # Providers bổ sung (HuggingFace, Ollama, ...)
│   ├── providers_part3.py       # Providers mới (Cloudflare, Replicate, GitHub Models, ...)
│   ├── ai_agent.py              # AI Discovery Agent (gọi LLM tìm provider mới)
│   └── live.py                  # Live Discovery (query OpenRouter API thật)
├── verification/
│   └── checker.py               # Async endpoint checker (progress callback, local semaphore)
├── aggregation/
│   └── aggregator.py            # Xuất JSON/YAML/CSV
├── notifications/
│   └── webhook.py               # Webhook notification khi provider status đổi
├── api/
│   └── app.py                   # REST API (FastAPI): /api/v1/providers, /health, ...
└── cli/
    └── main.py                  # Click CLI: list / check / update / discover-ai / discover-live / health / serve
```

## Provider hiện có (20)

| Provider | Free tier | OpenAI-compatible | Ghi chú |
|----------|-----------|-------------------|---------|
| OpenRouter | ✅ (:free models) | ✅ | |
| Groq | ✅ | ✅ | llama-3.1-8b, mixtral-8x7b |
| Google Gemini | ✅ | ❌ (custom) | gemini-2.0-flash free tier |
| Mistral AI | ✅ (thí điểm) | ✅ | |
| Cohere | ✅ (trial key) | ❌ (custom) | |
| Together AI | ❌ (paid-only) | ✅ | Free tier đã kết thúc |
| Hugging Face | ✅ | ❌ (custom) | serverless |
| Fireworks AI | ✅ | ✅ | |
| SiliconFlow | ⚠️ free + credits | ✅ | model nhỏ free |
| Anthropic | 💰 trial-only | ❌ (anthropic) | $5 credits |
| Perplexity | 💰 trial-only | ✅ | $5 credits |
| DeepSeek | 💰 trial-only | ✅ | 500M tokens |
| Ollama | ✅ | ✅ | local, no-auth |
| GigaChat | ✅ | ❌ (custom) | Nga, 100 req/ngày |
| Yandex Cloud | ✅ (Lite) | ❌ (custom) | Nga, 5K tokens/phút |
| Cloudflare Workers AI | ✅ (10K neurons/ngày) | ✅ | edge, thay `{account_id}` trong base_url |
| GitHub Models | ✅ (qua PAT) | ✅ | free rate limit theo tier tài khoản |
| Cerebras | ✅ | ✅ | inference nhanh nhất (WSE) |
| SambaNova | ✅ | ✅ | custom RDU chip |
| Replicate | ❌ (paid-only) | ❌ (custom) | trả phí theo giây chạy |

## Đóng góp

Muốn thêm provider mới? Sửa `src/discovery/providers_part2.py` (hoặc tạo
`providers_part3.py` mới) và thêm entry theo format `Provider(...)`. Sau đó
chạy `update` để verify.

Xem chi tiết quy trình trong [CONTRIBUTING.md](CONTRIBUTING.md).
Báo cáo lỗ hổng bảo mật: [SECURITY.md](SECURITY.md).

## Troubleshooting

### `discover-ai` báo "Chưa cấu hình AI provider"
→ Bạn chưa tạo file `.env`. Copy từ `.env.example` và điền API key:
```bash
cp .env.example .env
# sửa .env, điền AI_PROVIDER_BASE_URL / AI_API_KEY / AI_MODEL
```

### `check --provider` báo "Không tìm thấy"
CLI có gợi ý fuzzy — chạy lệnh và xem dòng "Bạn có ý là:" để sửa typo.
Xem danh sách đầy đủ: `run.py list`.

### `list --verify` thoát với exit code 1
Có provider endpoint chết — đây là hành vi đúng (để CI/hooks phát hiện).
Dùng `run.py list` (không `--verify`) nếu chỉ cần xem danh sách.

### Timeout khi chạy `discover-live`
Mặc định timeout 15s. Nếu mạng chậm, tăng qua code:
```python
from src.discovery.live import fetch_openrouter_free_models
fetch_openrouter_free_models(timeout=30.0)
```

### Docker: `.env` không được mount
Xem section [Docker](#docker) — chạy `cp .env.example .env` trước khi
`docker compose up`.

### Webhook không gửi notification
1. Kiểm tra `WEBHOOK_URL` đã set trong `.env` chưa (trống = tắt).
2. `WEBHOOK_ENABLED` phải là `true`.
3. Notification chỉ gửi khi CÓ provider đổi status — nếu mọi provider giữ
   nguyên status, không có gì để gửi.
4. Bật `--verbose` để xem log debug của webhook.

## FAQ

**Q: Tool có spam các endpoint provider không?**
A: Không. Verification chỉ gửi 1 GET request nhẹ tới `/models` cho mỗi provider,
giới hạn 5 request song song, retry tối đa 2 lần với exponential backoff.

**Q: `discover-ai` và `discover-live` khác nhau thế nào?**
A: `discover-ai` hỏi LLM (dựa trên training data — có thể sai/thiếu).
`discover-live` query trực tiếp OpenRouter API — dữ liệu thật tại thời điểm gọi.
Muốn dữ liệu đáng tin nhất → `discover-live`.

**Q: Tôi có cần API key để chạy không?**
A: Không. `list`, `check`, `update`, `discover-live`, `health` chạy không cần key.
Chỉ `discover-ai` cần AI key (trong `.env`).

**Q: Kết quả `discover-ai` có đáng tin không?**
A: KHÔNG hoàn toàn. LLM có thể "bịa" provider không tồn tại. Hãy luôn chạy
`--verify` sau khi dùng `discover-ai`, hoặc dùng `discover-live` cho dữ liệu thật.

**Q: Webhook notification hoạt động như thế nào?**
A: Sau mỗi lần verify (`list --verify`, `update`), CLI so sánh status trong registry
với kết quả verify thật. Nếu có thay đổi, POST payload JSON tới `WEBHOOK_URL`.
Cấu hình trong `.env`: `WEBHOOK_URL`, `WEBHOOK_TIMEOUT`, `WEBHOOK_ENABLED`.
Lỗi webhook không bao giờ crash pipeline.

**Q: API server có gì khác với CLI?**
A: REST API trả về dữ liệu JSON, hỗ trợ lọc theo tag/auth/free, dùng từ app/website
khác. Cùng data nguồn registry, không cần verify (status gốc, chưa ping).

**Q: CSV format khác gì JSON?**
A: JSON giữ cấu trúc lồng nhau (provider chứa mảng models). CSV flatten — mỗi
row = 1 cặp (provider, model), thân thiện với Excel/Google Sheets. Cột:
provider, base_url, status, auth_required, api_style, tags, model_id, model_name,
is_free, context_length, supports_streaming, rate_limit, last_updated.

**Q: Version được quản lý thế nào?**
A: Single source of truth trong `pyproject.toml`. `src/__version__.py` đọc từ
importlib.metadata (nếu đã pip install) hoặc parse trực tiếp pyproject.toml.
CLI `run.py --version` hiển thị version hiện tại.

## Exit Codes

| Code | Ý nghĩa |
|------|---------|
| 0 | Thành công |
| 1 | Lỗi (provider không tìm thấy, inactive, hoặc có provider chết khi verify) |
| 2 | Rate limited |

## Phát triển (Enterprise)

```bash
# Cài dev dependencies (pytest, ruff, mypy, ...)
pip install -r requirements-dev.txt

# Chạy test suite (181 tests, coverage ≥ 90%)
./venv/bin/python -m pytest tests/ --cov=src

# Lint + format
./venv/bin/ruff check src/ tests/
./venv/bin/ruff format src/ tests/

# Type check
./venv/bin/python -m mypy src/

# Pre-commit hooks (tự động chạy trước mỗi commit)
pip install pre-commit && pre-commit install
pre-commit run --all-files  # chạy trên toàn repo

# Docker (đầy đủ: xem section "Docker" bên trên)
docker compose run app list
```

CI tự chạy trên GitHub Actions với 5 jobs:
1. **Lint** — ruff check + format check
2. **Type check** — mypy với pydantic plugin
3. **Test** — matrix Python 3.10–3.13, coverage gate ≥ 90%
4. **CLI Smoke Test** — list, json output, --version, health
5. **Docker Build** — build image + smoke test trong container

Xem `.github/workflows/ci.yml`.

Lưu ý về dữ liệu registry:
- Provider tag `trial-only` = chỉ có credits khởi tạo, KHÔNG free lâu dài
  (`is_free=False` trên models).
- Provider tag `unverified` = chưa xác minh, endpoint có thể đã chết.
- Test `tests/test_discovery.py` đảm bảo nhất quán free/paid — nếu thêm provider
  sai tag, test sẽ fail.
