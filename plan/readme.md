# 🏗️ Enterprise Upgrade Plan — Free LLM Provider Discovery

> **Phiên bản plan:** 1.1 · **Ngày:** 2026-10-28 · **Thời lượng:** ~8 giờ làm việc liên tục
> **Mục tiêu:** Đưa repo lên chuẩn enterprise application — không bug, không issue, architecture sạch, docs đầy đủ, hạ tầng production-grade.

---

## 1. Đánh giá hiện trạng (Current State Analysis)

### 1.1 Baseline ban đầu → Hiện tại

| Metric | Baseline | Hiện tại |
|---|---|---|
| Tests | 103 | **129** (+26 regression tests) |
| Coverage | 93% (gate 85%) | **92% (gate 90%)** |
| Ruff lint | Clean | Clean |
| mypy | ❌ Không có | ✅ 17 files, 0 errors |
| CI jobs | 3 (lint, test, smoke) | **5** (+typecheck, +docker) |
| Docker | Multi-stage non-root | + HEALTHCHECK + OCI labels + .dockerignore |
| Docs | README | + LICENSE, SECURITY.md, CONTRIBUTING.md, pre-commit |

### 1.2 Kiến trúc

```
src/
├── __init__.py
├── __main__.py            # python -m src
├── __version__.py         # Single source of truth cho version (MỚI)
├── config.py              # Pydantic Settings (AI config)
├── logging_config.py      # stdlib logging — idempotent setup
├── models.py              # Pydantic models (Provider, Model, ProviderList)
├── aggregation/
│   └── aggregator.py      # Tổng hợp + xuất JSON/YAML (có version field)
├── cli/main.py            # Click CLI (6 commands + --version flag)
├── discovery/
│   ├── __init__.py        # Registry KNOWN_PROVIDERS
│   ├── providers_part1.py # Registry cứng (phần 1)
│   ├── providers_part2.py # Registry cứng (phần 2)
│   ├── ai_agent.py        # AI discovery qua LLM (retry 429/5xx)
│   └── live.py            # Live discovery qua OpenRouter API (retry 429/5xx)
└── verification/
    └── checker.py         # Async verify (semaphore + retry 429/5xx + logging)
```

---

## 2. Issues / Bugs phát hiện (Issues/Bugs Detected)

*(Toàn bộ đã được fix trong Phase 2-4, chi tiết trong CHANGELOG.md v1.3.0)*

### 🔴 BUG mức cao — ✅ ĐÃ FIX
| # | File | Vấn đề | Status |
|---|---|---|---|
| B1 | `live.py` | Dead param `base_url` | ✅ Fix + regression test |
| B2 | `logging_config.py` | setup_logging không idempotent | ✅ Fix + 6 tests |
| B3 | `ai_agent.py` | `_extract_json` fail khi string chứa brace | ✅ Fix (raw_decode) + test |
| B4 | `ai_agent.py` | HTTP 429/5xx không retry | ✅ Fix + 3 tests |
| B5 | `checker.py` | HTTP 429/5xx không retry | ✅ Fix + 5 tests |
| B6 | `checker.py` | `except Exception` quá rộng | ✅ Thu hẹp + log + safety net |

### 🟡 BUG mức trung — ✅ ĐÃ FIX
| # | Vấn đề | Status |
|---|---|---|
| B7 | Version hardcode 2 nơi | ✅ `src/__version__.py` single source |
| B8 | Duplicate import json trong `health` | ✅ Xoá |
| B9 | `ProviderList.version` = "1.0.0" stale | ✅ Lấy từ `__version__` |
| B10 | `AI_TIMEOUT` không validate | ✅ Validator `> 0` |
| B11 | `validate()` shadow BaseModel.validate | ✅ Rename `validation_errors()` |
| B12 | Dead code `_provider_to_dict` | ✅ Xoá |
| B13 | JSON/YAML payload thiếu `version` | ✅ Đã xuất |

---

## 3. Kế hoạch cải thiện (Improvement Roadmap)

### Phase 1 — Audit & Plan ✅
- [x] Quét toàn bộ repo, đọc toàn bộ source code, test, infra
- [x] Viết `plan/readme.md` (file này)

### Phase 2 — Sửa BUG nghiêm trọng ✅
- [x] B1–B13: toàn bộ 13 bug đã fix, mỗi fix có regression test
- [x] Commit `47a0de1` — 125 tests

### Phase 3 — Enterprise Infra ✅
- [x] LICENSE / SECURITY.md / CONTRIBUTING.md / .pre-commit-config.yaml / .dockerignore
- [x] mypy (17 files clean, pydantic plugin) + CI job
- [x] Coverage gate 90% · Dockerfile HEALTHCHECK + OCI labels · [project.urls] · CLI --version
- [x] Commit — 125 tests, mypy clean

### Phase 4 — Code Quality & Robustness ✅
- [x] CLI fuzzy suggestion khi gõ sai provider (difflib)
- [x] Retry + exponential backoff cho `discover-live`
- [x] CI: 5 jobs (lint, typecheck, test matrix, smoke, docker)
- [x] Commit — 129 tests

### Phase 5 — Docs & Data ✅
- [x] README: badges + Architecture diagram + Troubleshooting + FAQ
- [x] Refresh `data/providers.json` sample
- [x] CHANGELOG v1.3.0 đầy đủ

### Phase 6 — Final Review Loop
- [ ] Self-review toàn bộ diff các commit
- [ ] Smoke test thực tế CLI (list, check, health, --version, discover-live)
- [ ] Edge cases còn sót
- [ ] Cập nhật plan cuối phiên

---

## 4. Tiêu chí chấp nhận (Acceptance Criteria)

- [x] 100% BUG ở mục 2 được fix + có regression test
- [x] Full test suite pass (129 tests), coverage ≥ 90% (hiện 92%)
- [x] Ruff (lint + format) sạch
- [x] mypy type-check sạch
- [x] CI workflow: lint + typecheck + test matrix + smoke + docker
- [x] Có đủ LICENSE / SECURITY.md / CONTRIBUTING.md / .pre-commit-config.yaml
- [x] Docker: HEALTHCHECK + non-root + .dockerignore
- [x] Version single-source, không hardcode
- [x] README có architecture diagram, troubleshooting, FAQ
- [x] Không có dead code, không có warning khi build

---

## 5. Self-Review Log

### Commit `47a0de1` — Phase 2 (fix 13 bugs)
**Tự đánh giá:** ✅ Đạt
- Mọi bug fix đều có regression test đi kèm (không chỉ sửa mà chứng minh sửa đúng)
- Phát hiện và tự sửa trong quá trình làm: duplicate imports do edit nhầm (aggregator.py), walrus operator sai (live.py draft), thiếu `raise_for_status` trong FakeResponse
- Bài học: `from src import __version__` import NHẦM module thay vì attribute — phải dùng `from src.__version__ import __version__`

### Commit `dbec8cf` — Phase 3 (enterprise infra)
**Tự đánh giá:** ✅ Đạt
- mypy ban đầu 68 errors → fix về 0 bằng pydantic plugin + type annotation
- CI thêm 2 job (mypy + docker) — tổng 5 jobs
- coverage gate 90%, thực tế 92%

### Commit `a86311d` — Phase 4 (robustness)
**Tự đánh giá:** ✅ Đạt
- Retry logic dùng RETRYABLE_STATUS_CODES constant — dễ maintain
- 3 test mới cho retry (hết lượt / recover / 404-raise-ngay)
- Fuzzy suggestion hoạt động: `grop` → gợi ý `Groq`

---

*Plan này được cập nhật liên tục trong suốt phiên làm việc 8 giờ.*
