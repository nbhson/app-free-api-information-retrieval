# Changelog

Tất cả thay đổi quan trọng của project được ghi nhận trong file này.
Format dựa trên [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning theo [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] — 2026-10-30

### Added
- **Deep verification cho provider có API key**:
  - `check --api-key KEY` (hoặc env `PROVIDER_API_KEY`): verify endpoint với
    Authorization header thật — phân biệt được "endpoint sống" và "key hợp lệ".
  - `check --sync-models`: fetch danh sách model THẬT từ `/models` (chuẩn OpenAI,
    chấp nhận các biến thể `data` / `models` / list string / key `model`) thay cho
    danh sách model tĩnh trong registry. Item lỗi bị bỏ qua, không làm chết cả list.
  - `check --smoke MODEL_ID`: chat completion thật end-to-end với max_tokens nhỏ —
    chứng minh key + model + inference hoạt động, báo latency/tokens/finish_reason.
    Lỗi (HTTP, timeout, response sai chuẩn, content rỗng) → `SmokeTestError`, exit 1.
- **Provider mới: Upstage (Solar)** — provider AI Hàn Quốc, OpenAI-compatible,
  base URL `https://api.upstage.ai/v1`. Đã test thật: 9 model live, smoke test
  `solar-pro4` trả kết quả đúng. Registry hiện 23 provider.

### Fixed
- **CLI `list --verify --output` mất file kết quả**: khi có provider chết, lệnh
  `sys.exit(1)` chạy TRƯỚC khi lưu `--output` → CI/hooks mất toàn bộ dữ liệu đã
  verify. Giờ output luôn được lưu trước khi exit với code 1.
- **AI agent retry 429/5xx không có backoff**: `discover_with_ai` retry ngay lập
  tức, đánh nhau với server đang rate limit. Thêm exponential backoff (1s/2s)
  giống convention của `checker.py` / `live.py`.
- **CSV export mất provider không có model free**: comment chủ đích là "vẫn xuất
  1 row để không mất dữ liệu" nhưng code không xuất row nào → provider biến mất
  khỏi file CSV (JSON thì vẫn giữ). Giờ mỗi provider luôn có ít nhất 1 row.
- **SQLite connection không được đóng tường minh**: `with conn:` của sqlite3 chỉ
  commit/rollback transaction, KHÔNG close connection — phụ thuộc refcount của
  CPython để dọn dẹp (leak FD trên PyPy/refactor sau này). Chuyển sang
  `contextlib.closing()` cho mọi thao tác DB.
- **Dead code trong `run_search`**: điều kiện `scoped = keyword if "site:" ...`
  trả về cùng 1 giá trị ở cả 2 nhánh — xoá dòng no-op.

### Changed (Enterprise)
- **API security hardening**:
  - So sánh API key timing-safe (`secrets.compare_digest`) — chống timing attack.
  - Security headers trên mọi response: `X-Content-Type-Options`, `X-Frame-Options`,
    `Referrer-Policy`, `Cache-Control`.
  - Unhandled exception handler: log đầy đủ phía server, trả 500 JSON gọn phía
    client — không leak stack trace ra ngoài.
  - GZip middleware (minimum 1KB) — payload danh sách provider nén ~80%.
- **Docker**: `PYTHONDONTWRITEBYTECODE=1` + `PYTHONUNBUFFERED=1` (chuẩn container);
  bỏ copy `requirements-dev.txt` không dùng ở build stage; service `api` mount
  `./data` để history DB persist qua restart.

## [1.5.0] — 2026-10-28

### Added
- **Deep Web Search** (module mới `src/discovery/websearch/`): search thật trên
  5 nguồn internet (Reddit, Hacker News, DuckDuckGo, GitHub, **LMSpeed shared keys**)
  với keyword linh hoạt (tùy chỉnh qua `--keywords/-k` hoặc preset đa ngôn ngữ).
  CLI: `run.py discover-web` — không cần key, kết quả nên `--verify` trước khi dùng.
  Heuristic mode (regex bắt /v1 endpoint) hoặc AI mode (LLM đọc nội dung trang thật).
- **Nguồn 'shared'** (Crown AI status API + LMSpeed shared keys): truy vấn
  `https://crown.ai.id/api/status` (JSON public, live model online) và
  `https://lmspeed.net/free-api-keys` (RSC payload chứa baseUrl thật của key
  cộng đồng đang chia sẻ) — trích xuất provider mới từ nội dung thật.
- **2 provider mới** (Indonesian community pool): **Crown AI** (bansos) và **free.ai.id**
  — pool cộng đồng chia sẻ API key miễn phí, OpenAI-compatible, không cần đăng ký.
- **Keyword mới**: 11 keywords đa ngôn ngữ (EN/VN/ID), bao gồm community-sharing
  keywords ("shared free api key", "community api key pool", "bansos ai gratis"...)
- **3 provider tự động phát hiện** từ LMSpeed shared keys (live discovery):
  Nightrouter, Agentrouter, Bananarouter và 6+ community pool khác qua source `shared`.

### Changed
- Source registry mở rộng: 4 backend search → 5 (thêm `shared`).
- Keywords mặc định: 7 → 11 (thêm community-sharing variants).

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
