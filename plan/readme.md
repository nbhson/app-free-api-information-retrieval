# 🏗️ Enterprise Upgrade Plan — Free LLM Provider Discovery

> **Phiên bản plan:** 1.0 · **Ngày:** 2026-10-28 · **Thời lượng:** ~8 giờ làm việc liên tục
> **Mục tiêu:** Đưa repo lên chuẩn enterprise application — không bug, không issue, architecture sạch, docs đầy đủ, hạ tầng production-grade.

---

## 1. Đánh giá hiện trạng (Current State Analysis)

### 1.1 Số liệu ban đầu (baseline)

| Metric | Giá trị | Đánh giá |
|---|---|---|
| Tests | 103 passed | ✅ Tốt |
| Coverage | 93% (gate 85%) | 🟡 Tốt, nhưng 1 module chỉ 62% |
| Ruff lint | Clean | ✅ |
| CI | 3 jobs (lint, matrix 3.10–3.13, smoke) | ✅ |
| Docker | Multi-stage, non-root | 🟡 Thiếu HEALTHCHECK |
| Tests | 103 / 4.2s | ✅ |
| Source | ~1,600 LOC / 15 files | — |

### 1.2 Kiến trúc hiện tại

```
src/
├── __init__.py
├── config.py              # Pydantic Settings (AI config)
├── logging_config.py      # stdlib logging
├── models.py              # Pydantic models (Provider, Model, ProviderList)
├── aggregation/
│   └── aggregator.py      # Tổng hợp + xuất JSON/YAML
├── cli/main.py            # Click CLI (list, check, update, discover-ai, discover-live, health)
├── discovery/
│   ├── __init__.py        # Registry KNOWN_PROVIDERS
│   ├── providers_part1.py # Registry cứng (phần 1)
│   ├── providers_part2.py # Registry cứng (phần 2)
│   ├── ai_agent.py        # AI discovery qua LLM
│   └── live.py            # Live discovery qua OpenRouter API
└── verification/
    └── checker.py         # Async verify endpoint (semaphore + retry)
```

---

## 2. Issues / Bugs phát hiện (Issues/Bugs Detected)

### 🔴 BUG — mức độ cao (sẽ sửa trong Phase 2)

| # | File | Vấn đề | Chi tiết |
|---|---|---|---|
| B1 | `src/discovery/live.py` | **Dead parameter `base_url`** | `fetch_openrouter_free_models(base_url=...)` nhận param nhưng không dùng — httpx.get luôn gọi `OPENROUTER_MODELS_URL`. Misleading API, khó test với URL khác. |
| B2 | `src/logging_config.py` | **setup_logging không idempotent** | Nếu root logger đã có handler (ví dụ pytest, gọi lại 2 lần), handler cũ không được cập nhật level → DEBUG log bị chặn hoặc log trùng lặp. |
| B3 | `src/discovery/ai_agent.py` | **`_extract_json` không xử lý `}` trong string** | Đếm brace bằng loop đơn giản, nếu description AI trả về chứa ký tự `{`/`}` trong chuỗi → parse sai. |
| B4 | `src/discovery/ai_agent.py` | **HTTP 429 không retry** | Message nói "thử lại sau" nhưng code raise ngay lập tức → không retry. |
| B5 | `src/verification/checker.py` | **HTTP 429 không retry** | Trả về `RATE_LIMITED` ngay, không retry với backoff — trong khi docstring nói có retry. |
| B6 | `src/verification/checker.py` | **`except Exception` quá rộng** | Bất kỳ lỗi nào khác (không phải ConnectError/Timeout) → set UNKNOWN ngay, không retry, khó debug. |

### 🟡 BUG — mức trung (sẽ sửa trong Phase 2)

| # | File | Vấn đề | Chi tiết |
|---|---|---|---|
| B7 | `src/cli/main.py` | **Version hardcode 2 nơi** | `health` command hardcode `"1.2.0"`, pyproject.toml cũng có `1.2.0` → dễ drift khi bump version. |
| B8 | `src/cli/main.py` | **Duplicate import json trong `health`** | `json` đã import ở module scope, `health` lại `import json` lần nữa. |
| B9 | `src/models.py` | **`ProviderList.version` default "1.0.0"** | Mismatch với app version 1.2.0, không single-source. |
| B10 | `src/config.py` | **`AI_TIMEOUT` không validate** | Chấp nhận giá trị 0 hoặc âm → request lỗi runtime khó hiểu. |
| B11 | `src/config.py` | **`validate()` method name shadow `BaseModel.validate()`** | Pydantic v2 có classmethod `validate()` — overriding bằng instance method dễ gây nhầm lẫn, nên đổi tên thành `validation_errors()`. |
| B12 | `src/aggregation/aggregator.py` | **Dead code `_provider_to_dict`** | Function không ai gọi, chưa xóa. |
| B13 | `src/aggregation/aggregator.py` | **JSON/YAML payload thiếu field `version`** | ProviderList có `version` nhưng khi save không xuất ra file. |

### 🟠 Enterprise Infra Gap (sẽ sửa trong Phase 3)

| # | Vấn đề | Chi tiết |
|---|---|---|
| E1 | **Thiếu file `LICENSE`** | `pyproject.toml` khai báo MIT nhưng không có file LICENSE — vi phạm chuẩn OSS/enterprise. |
| E2 | **Thiếu `SECURITY.md`** | Không có hướng dẫn report vulnerability. |
| E3 | **Thiếu `CONTRIBUTING.md`** | Không có quy trình đóng góp cho developer ngoài. |
| E4 | **Không có `pre-commit` config** | hooks: ruff, ruff-format, end-of-file-fixer, trailing-whitespace, check-yaml, check-toml. |
| E5 | **CI thiếu mypy** | Type-check chưa chạy trong CI. |
| E6 | **Coverage gate 85% → có thể nâng** | baseline 93%, nên target ≥ 90%. |
| E7 | **Không có `__main__.py`** | `python -m src` không chạy được. |
| E8 | **Dockerfile thiếu `HEALTHCHECK`** | Không thể giám sát container health. |
| E9 | **`requirements.txt` không pin version** | Chỉ dùng `>=` → có thể break khi library ra breaking change. Nên có `requirements.lock` hoặc pin range chặt hơn. |
| E10 | **`pyproject.toml` thiếu `[project.urls]`** | Homepage / repository metadata. |
| E11 | **CLI thiếu `--version` flag** | Người dùng không biết version đang chạy. |
| E12 | **Dockerfile không dùng `.dockerignore`** | Copy `src/` toàn bộ có thể đưa vào `.pyc`, `__pycache__`. |
| E13 | **README thiếu Architecture / Troubleshooting / FAQ** | Docs tốt hơn nữa cho dev mới. |
| E14 | **`data/providers.json` sample data chưa refresh** | `last_updated` 2026-10-27, model stale (llama-2, openchat-7b...). |

### ⚪ Nice-to-have (nếu còn thời gian)

| # | Vấn đề |
|---|---|
| N1 | Thêm type hints đầy đủ + chạy mypy strict hơn |
| N2 | Cải thiện error messages cho CLI, thêm suggestion khi không tìm thấy provider |
| N3 | `ProviderList.version` lấy từ `importlib.metadata` thay vì hardcode |
| N4 | Live discovery thêm retry/backoff |
| N5 | README thêm badges (CI status, coverage, Python version, license) |
| N6 | Logging: thêm `%(funcName)s` hoặc structured JSON format option |
| N7 | Thêm pytest marker `@pytest.mark.slow` cho test tốn thời gian |
| N8 | Refactor `checker.py` tách pure logic / IO để dễ test |
| N9 | `providers_part1/2.py` merge thành 1 module nếu không cần thiết chia |

---

## 3. Kế hoạch cải thiện (Improvement Roadmap)

### Phase 1 — Audit & Plan (~0.5h) ✅ *bắt đầu ngay*
- [x] Quét toàn bộ repo, đọc toàn bộ source code, test, infra
- [x] Viết `plan/readme.md` (file này)

### Phase 2 — Sửa BUG nghiêm trọng (~1.5h)
**Mục tiêu: hết mọi BUG được phát hiện ở mục 2**

- [ ] B1: Fix `live.py` — dùng đúng `base_url` param, test được với URL tuỳ ý
- [ ] B2: Rewrite `logging_config.py` — idempotent setup, handler level sync, có test
- [ ] B3: Rewrite `_extract_json` dùng `json.JSONDecoder().raw_decode` — handles string chứa brace
- [ ] B4: `ai_agent.py` — retry cho 429/5xx với backoff
- [ ] B5: `checker.py` — retry cho 429 + 5xx tạm thời
- [ ] B6: `checker.py` — thu hẹp `except Exception` xuống `httpx.RequestError`, log chi tiết lỗi
- [ ] B7: Tạo `src/__version__.py` (single source of truth), đọc từ pyproject
- [ ] B8: Xoá duplicate import `json` trong `health`
- [ ] B9: `ProviderList.version` default lấy từ `__version__`
- [ ] B10: Validate `AI_TIMEOUT > 0` trong `config.py`
- [ ] B11: Rename `validate()` → `validation_errors()`
- [ ] B12: Xoá dead code `_provider_to_dict`
- [ ] B13: Xuất `version` field trong JSON/YAML
- [ ] Viết test cho mọi fix, chạy full test + ruff
- [ ] **Commit + Self-Review**

### Phase 3 — Enterprise Infra (~2h)
- [ ] E1: Thêm `LICENSE` (MIT)
- [ ] E2: Thêm `SECURITY.md`
- [ ] E3: Thêm `CONTRIBUTING.md`
- [ ] E4: Thêm `.pre-commit-config.yaml` (ruff, ruff-format, yaml/toml checks, end-of-file)
- [ ] E5: Thêm mypy vào CI + type hint chuẩn hoá
- [ ] E6: Nâng coverage gate 85% → 90%
- [ ] E7: Thêm `src/__main__.py` để chạy `python -m src`
- [ ] E8: Dockerfile: thêm `HEALTHCHECK`, pin base image digest, cache pip, `.dockerignore`
- [ ] E9: Pin deps: tạo `constraints.txt` hoặc cập nhật `requirements.txt` với min version cụ thể
- [ ] E10: Thêm `[project.urls]` vào pyproject.toml
- [ ] E11: Thêm `--version` flag cho CLI
- [ ] E12: Thêm `.dockerignore`
- [ ] Viết test cho phần mới
- [ ] **Commit + Self-Review**

### Phase 4 — Code Quality & Robustness (~2h)
- [ ] Refactor `checker.py` tách logic sync/async rõ ràng, thêm test cho retry logic
- [ ] Refactor `live.py` — thêm retry, timeout configurable, fixture test
- [ ] Cải thiện `logging_config.py` — thêm structured format, support cho pytest caplog
- [ ] CLI: thêm flag `--version`, suggestion khi sai tên provider (difflib)
- [ ] Nâng coverage lên ≥ 95%
- [ ] Ruff + ruff format sạch, type hints đầy đủ
- [ ] Viết thêm test biên (edge cases) cho aggregator, live, checker
- [ ] **Commit + Self-Review**

### Phase 5 — Docs & Data (~1h)
- [ ] README: thêm Architecture diagram, Badges, Troubleshooting, FAQ
- [ ] `SECURITY.md`, `CONTRIBUTING.md` đi kèm nội dung chuẩn enterprise
- [ ] Refresh `data/providers.json` sample
- [ ] `CHANGELOG.md` cập nhật entry v1.3.0
- [ ] `pyproject.toml` — add urls, authors, maintainers
- [ ] **Commit + Self-Review**

### Phase 6 — Final Review Loop (~2h)
- [ ] Chạy full pipeline: ruff + pytest + coverage + smoke + docker build
- [ ] Đọc lại toàn bộ diff và self-review kỹ từng commit
- [ ] Kiểm tra edge case, fix bất kỳ lỗi nào phát hiện
- [ ] Cập nhật plan/readme.md cuối phiên (đánh dấu hoàn thành)
- [ ] **Commit + Self-Review**

---

## 4. Tiêu chí chấp nhận (Acceptance Criteria)

- ✅ 100% BUG ở mục 2 được fix + có regression test
- ✅ Full test suite pass (≥ 100 tests), coverage ≥ 90%
- [ ] Ruff (lint + format) sạch
- [ ] mypy type-check sạch
- [ ] CI workflow bao gồm: lint, type-check, test matrix, smoke
- [ ] Có đủ LICENSE / SECURITY.md / CONTRIBUTING.md / .pre-commit-config.yaml
- [ ] Docker: HEALTHCHECK + non-root + pinned deps
- [ ] Version single-source, không hardcode
- [ ] README có architecture diagram, troubleshooting, FAQ
- [ ] Không có dead code, không có warning khi build

---

## 5. Self-Review Log

*Mỗi commit sẽ được review lại ở đây (đánh giá chi tiết sau mỗi lần commit).*

---

*Plan này sẽ được cập nhật liên tục trong suốt phiên làm việc 8 giờ.*
