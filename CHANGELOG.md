# Changelog

Tất cả thay đổi quan trọng của project được ghi nhận trong file này.
Format dựa trên [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning theo [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Added
- **`list --from <file>`** — xem kho provider TÍCH LUỸY từ discover-web bằng
  lệnh chuẩn (thay vì mở file JSON thủ công):
  `docker compose run --rm app list --from data/web_providers.json`.
  Đọc được cả `web_providers.json`, `scan_state.json`, `discovered.json`
  (cùng schema key `providers`); kết hợp được `--verify`, `--format`,
  `--tag`, `--output` như list thường. File thiếu/sai → lỗi rõ ràng + exit 1.

## [1.9.0] — 2026-10-31

### Added
- **Nguồn shared-key community pool mở rộng** (`search_shared_keys`, nguồn `shared`):
  - **Crown bansos** (`crown.ai.id/bansos`): scrape trang phát key free của
    cộng đồng Indonesia — trích xuất mọi endpoint API `/v1` trong HTML.
  - **masb.web.id** (`ai.masb.web.id`): trang cộng đồng Indonesia chia sẻ
    key/API free — scrape generic, loại chính trang ra khỏi kết quả.
  - Kết quả shared không bị cắt cụt theo `max_results` của search nữa
    (chặn trên 50) — tránh mất provider khi thêm nguồn mới.
- **Nguồn social** (`--sources social`): tìm bài đăng free LLM API trên
  **X/Twitter, Threads, Instagram** qua Google index (`site:` scope) — dùng
  Google Custom Search khi có key, DuckDuckGo html fallback khi không có.
  1 nền tảng lỗi → các nền tảng khác vẫn chạy; dedupe URL giữa các nền tảng.
- **AI deep crawl 2 cấp** (`--deep-search`, mặc định BẬT): fetch trang kết
  quả cấp 1 → rút link con đáng follow (chứa hint `free/api/key/bansos/
  gratis/harga...` hoặc cùng domain) → fetch cấp 2 để AI đọc thêm. Tổng số
  trang vẫn bị chặn bởi `--pages` — sâu hơn nhưng không unbounded. Link
  social/blocked và link ngoài không có hint không bị follow.

### Changed
- **`discover-web` mặc định quét cả nguồn social + shared mở rộng** —
  `AVAILABLE_SOURCES` giờ gồm: `duckduckgo, github, google, hackernews,
  reddit, shared, social`.

## [1.8.1] — 2026-10-30

### Added
- **Nguồn Google cho `discover-web`** (`--sources google`, alias `g`):
  - **Google Custom Search JSON API** khi `.env` có `GOOGLE_API_KEY` +
    `GOOGLE_CSE_ID` — web index THẬT của Google, kết quả đáng tin nhất
    (free 100 query/ngày; hướng dẫn lấy key trong `.env.example`).
  - **Fallback Google News RSS** (public, không cần key) khi chưa cấu hình
    Custom Search hoặc CSE lỗi — parse XML thuần, không thêm dependency.
  - CSE trả rỗng/lỗi → tự chuyển tầng RSS, không crash (graceful).
- **`discover-web` mặc định dùng `--mode ai`**: không truyền `--mode` giờ là
  `ai` — LLM đọc NỘI DUNG trang thật để trích xuất provider + model free
  (chính xác hơn heuristic regex). AI chưa cấu hình hoặc lỗi → tự fallback
  về heuristic như trước, không crash.
- **Cờ `--no-dedup` cho `discover-web`**: tắt loại URL đã xem — quét lại cả
  trang cũ (kể cả cùng keyword cũ) để AI đọc nội dung MỚI NHẤT. Dùng khi
  muốn đào sâu thay vì chỉ khai thác trang mới.
- **`ScanState.record_run` + `run_history`**: mỗi lần scan ghi 1 entry
  timestamp (mode, keywords, số provider mới/cập nhật) vào
  `scan_state.json` (state version 2, load được file v1 cũ).
- **`ScanState.merge_providers` cập nhật provider đã có**: provider tìm lại
  (cùng base_url/name) được refresh info — models, description, website,
  tags — thay vì bị bỏ qua hoàn toàn; status verify cũ được giữ nguyên.
  Danh sách provider được cập nhật nằm ở `state.last_merge_updated`.

### Changed
- **`discover-web` hiển thị rõ kết quả lần scan**: provider MỚI in riêng;
  khi không có mới nhưng có provider được cập nhật info → in bảng cập nhật;
  khi rỗng → gợi ý `--no-dedup` / xoay keyword. Cuối lần chạy in dòng tóm
  tắt `Lần scan này: +N mới, ~M cập nhật (timestamp)`.

## [1.8.0] — 2026-10-30

### Added
- **Scan state — lưu trạng thái quét & tiếp tục giữa các lần chạy** (`discover-web`):
  - Mỗi lần quét xong lưu `data/scan_state.json` (config qua env `SCAN_STATE_PATH`
    hoặc cờ `--state`): URL kết quả search đã xử lý, keyword đã dùng, provider
    tích luỹ kèm danh sách model free.
  - Lần chạy sau tự **resume** (mặc định `--resume`): bỏ qua URL đã xử lý,
    gộp provider mới vào kho tích luỹ, xuất kết quả TÍCH LUỸY (cũ + mới) ra
    `--output`. Cờ `--fresh` để quét lại từ đầu.
  - Module mới `src/storage/scan_state.py` (`ScanState`): load/save atomic,
    file hỏng/mất tự reset không crash, dùng được như context manager (crash
    giữa chừng vẫn lưu tiến trình).
- **Xoay vòng keyword**: pool mới `KEYWORD_POOL` (~39 từ khoá EN/VI/community
  sharing) — mỗi lần chạy không truyền `-k` sẽ lấy tối đa `--kw-batch` (default 8)
  từ khoá CHƯA dùng, đảm bảo mỗi lần quét khai thác vùng internet mới thay vì
  lặp lại kết quả cũ. Pool cạn → tự bắt đầu chu kỳ mới.
- **`run_deep_search` nhận `exclude_urls` + `on_results`**: loại URL đã xử lý
  lần trước khỏi kết quả search; callback để caller đánh dấu trạng thái.

### Changed
- **Ưu tiên free token, bỏ emphasis rate limit**: prompt AI extraction
  (`extractor.py`, `ai_agent.py`) viết lại — nhiệm vụ số 1 là tìm trang có
  free token / key cộng đồng, `free_models` là bắt buộc trích xuất, không còn
  yêu cầu trích xuất rate limit/speed.
- **`discover-web --output` giờ xuất kho tích luỹ** (provider cũ + mới) thay vì
  chỉ kết quả lần chạy hiện tại; lưu state xảy ra TRƯỚC khi verify/exit nên
  tiến trình không mất khi verify lỗi.

### Fixed
- **Test isolation cho scan state**: autouse fixture `_tmp_scan_state` trỏ
  `SCAN_STATE_PATH` vào tmp_path — test không đụng `data/scan_state.json` thật.

## [1.7.0] — 2026-10-30

### Changed
- **Nâng cấp toàn bộ dependencies floors** (theo versions thực tế đang test):
  `httpx>=0.28`, `click>=8.2`, `rich>=13.9`, `pydantic>=2.12`,
  `pydantic-settings>=2.10`, `python-dotenv>=1.2`, `fastapi>=0.115`,
  `uvicorn>=0.30`, `pyyaml>=6.0.3`; dev: `pytest>=8.3`, `pytest-asyncio>=1.0`,
  `pytest-cov>=6.0`, `ruff>=0.17`.
- **Thêm `mypy` + `types-PyYAML` vào dev dependencies** — trước đây mypy chỉ cài
  thủ công trong CI, không khai báo trong `pyproject.toml`/`requirements-dev.txt`.
- **Pre-commit hooks nâng cấp**: `ruff-pre-commit` v0.6.9 → v0.17.3 (hook id
  `ruff` đổi thành `ruff-check` theo convention mới), `pre-commit-hooks`
  v4.6.0 → v6.0.0, `mirrors-mypy` v1.11.2 → v2.4.1.
- **CI nâng cấp**: `actions/checkout@v5`, `actions/setup-python@v6`, thêm
  Python 3.14 vào test matrix; job typecheck cài qua `requirements-dev.txt`
  thay vì pip install thủ công.

### Refactor
- **`discover-ai` dùng lại `dedupe_providers()`** có sẵn trong
  `deep_search.py` thay cho logic dedup inline lặp lại (cùng quy tắc
  base_url/name, không phân biệt hoa thường).
- **Gom pattern "lưu output + in thông báo" thành `_save_and_report()`** —
  trước đây lặp ở 5 lệnh CLI (`list`, `update`, `discover-ai`,
  `discover-live`, `discover-web`).
- **`discover-ai --verify` dùng Rich progress bar** giống `list --verify` /
  `discover-web --verify` (trước đây chạy `asyncio.run` im lặng, không có
  progress).
- **`ProviderList.model_post_init`**: đổi tham số `__context` (bị name-mangling
  của Python thành `_Provider__context`) thành `_context: object` rõ ràng.

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
