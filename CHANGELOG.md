# Changelog

Tất cả thay đổi quan trọng của project được ghi nhận trong file này.
Format dựa trên [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning theo [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] — 2026-10-28

### Added
- **CSV export**: `list --format csv` (stdout) và `--output file.csv` — 1 row cho mỗi
  (provider, model), mở trực tiếp bằng Excel/Google Sheets. Helper mới
  `providers_to_csv()` + `save_to_csv()` trong aggregator, dispatch tự động theo
  đuôi file cho mọi lệnh có `--output`.
- **Progress bar cho verification**: `verify_all_providers` nhận optional
  `progress_callback(completed, total, provider)`; CLI vẽ Rich Progress bar khi
  chạy `list --verify` và `update`. Backward compatible — callback là optional.
- **Webhook notification**: module mới `src/notifications/webhook.py`. Sau khi verify
  (`list --verify`, `update`), CLI so sánh status registry vs kết quả verify và POST
  payload JSON tới `WEBHOOK_URL` (cấu hình trong `.env`: `WEBHOOK_URL`,
  `WEBHOOK_TIMEOUT`, `WEBHOOK_ENABLED`). Fire-and-forget an toàn — lỗi webhook
  không bao giờ crash pipeline verify.
- **5 providers mới** (`providers_part3.py`): Cloudflare Workers AI (free tier,
  OpenAI-compatible), GitHub Models (free qua PAT), Cerebras (free tier),
  SambaNova (free tier), Replicate (paid-only) → registry 15 → **20 providers**.
- **REST API server**: `python run.py serve --host 0.0.0.0 --port 8000` (FastAPI +
  uvicorn). Endpoints: `GET /api/v1/providers` (lọc tag/no_auth/free_only),
  `GET /api/v1/providers/{name}`, `GET /api/v1/health`, `GET /api/v1/version`.
  Swagger UI tại `/docs`. Module mới `src/api/app.py` (100% test coverage).
  Docker Compose thêm service `api` expose port 8000.

## [1.3.0] — 2026-10-28

### Fixed
- **live.py**: dead param `base_url` giờ được dùng thật (trước luôn dùng constant)
- **logging_config.py**: `setup_logging` giờ idempotent — sync handler level, không duplicate handler
- **ai_agent.py**: `_extract_json` dùng `JSONDecoder.raw_decode` — parse đúng khi string chứa `{ }`
- **ai_agent.py**: HTTP 429/5xx được retry với backoff (trước raise ngay)
- **checker.py**: HTTP 429/5xx được retry với exponential backoff
- **checker.py**: log chi tiết lỗi + safety net không crash cả batch verify
- **config.py**: validate `AI_TIMEOUT > 0`
- **config.py**: rename `validate()` → `validation_errors()` (không shadow BaseModel.validate)
- **aggregator.py**: xoá dead code `_provider_to_dict`; payload JSON/YAML giờ có field `version`
- **Single source of truth cho version**: `src/__version__.py` — CLI `--version`, health report, output file, User-Agent header đều đọc từ 1 nguồn

### Added
- **CLI `--version` flag** — hiển thị version từ single source
- **`python -m src`** — chạy module trực tiếp (`src/__main__.py`)
- **Fuzzy suggestion** khi `check --provider` gõ sai tên (difflib)
- **Retry với exponential backoff cho `discover-live`** (429/5xx/timeout)
- **LICENSE** (MIT), **SECURITY.md**, **CONTRIBUTING.md**
- **`.pre-commit-config.yaml`** — ruff + file hygiene + mypy hooks
- **`.dockerignore`** — giảm image size
- **Dockerfile HEALTHCHECK** + OCI labels
- **mypy**: toàn bộ 17 files type-clean, pydantic plugin, chạy trong CI
- **CI job mới**: typecheck (mypy), docker build + smoke test trong container

### Changed
- Coverage gate: 85% → **90%** (hiện tại 92%)
- CI: 3 jobs → 5 jobs (thêm mypy + docker)
- `ProviderList.version` default lấy từ `__version__` (trước hardcode "1.0.0")

## [1.2.0] — 2026-10-28

### Added
- **Live Discovery (`discover-live`)**: query dữ liệu internet THẬT từ OpenRouter `/models`
  API (public, không cần API key) → trả về danh sách model free thật tại thời điểm gọi,
  dựa trên pricing thực tế (`prompt=0` và `completion=0`). Không phụ thuộc trí nhớ LLM
  hay registry cứng — luôn là trạng thái mới nhất của internet.
- Module mới `src/discovery/live.py` (100% test coverage)

## [1.1.0] — 2026-10-27

### Added
- **3 providers mới**: Ollama (local inference), GigaChat (Nga), Yandex Cloud
- **Health check command**: `python run.py health` — kiểm tra nhanh registry + config
- **Structured logging**: `--verbose` flag cho debug, dùng stdlib logging
- **AI dedup**: tự động lọc provider trùng lặp khi dùng `discover-ai`
- **Exit codes chuẩn cho CLI**: `check` trả 0 (active), 1 (inactive/not found), 2 (rate limited); `list --verify` trả 1 nếu có provider chết

### Changed
- **Verification trả về copy**: `verify_provider`/`verify_all_providers` không còn mutate shared state
- **Semaphore cục bộ**: moved từ module-level vào function scope — thread-safe hơn
- **Registry refresh**: xoá 3 providers chết (Novu.ai, Leiku AI, OpenChat), cập nhật models stale (Groq, Gemini 1.5 → 2.0, Together AI marked paid-only)
- **Test deps tách riêng**: `requirements-dev.txt`, pytest không còn trong production image

## [1.0.0] — 2026-10-27

### Added
- CLI commands: `list`, `check`, `update`, `discover-ai`
- Registry 15 LLM providers (curate thủ công)
- AI Discovery Agent (OpenAI-compatible endpoint bất kỳ qua `.env`)
- Async verification với semaphore (max 5 song song) + retry exponential backoff
- Xuất JSON/YAML, filter `--tag` / `--no-auth` / `--verify`
- Test suite: 71 tests, coverage 89%
- CI: GitHub Actions (lint ruff + test matrix 3.10–3.13 + smoke test)
- Dockerfile (multi-stage, non-root) + docker-compose

### Fixed
- Bug: `--output` bị bỏ qua khi dùng cùng `--format json|yaml`
- `datetime.utcnow()` deprecated → `datetime.now(timezone.utc)`
- Registry data: DeepSeek/Perplexity/Anthropic đánh dấu `trial-only` (`is_free=False`)
- Loại bỏ model Groq đã ngừng (`mixtral-8x7b-32768`)
- Config refactor: Pydantic Settings thay cho dotenv hack
- Dọn deps thừa: `aiohttp`, `asyncio-throttle` (không dùng)
