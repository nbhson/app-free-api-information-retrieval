# Changelog

Tất cả thay đổi quan trọng của project được ghi nhận trong file này.
Format dựa trên [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning theo [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
