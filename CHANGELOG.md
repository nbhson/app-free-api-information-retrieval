# Changelog

Tất cả thay đổi quan trọng của project được ghi nhận trong file này.
Format dựa trên [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning theo [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
