# Contributing to Free LLM Provider Discovery

Cảm ơn bạn đã quan tâm đóng góp! Dưới đây là hướng dẫn để đảm bảo
chất lượng code và quy trình review suôn sẻ.

## Prerequisites

- Python 3.10, 3.11, 3.12, hoặc 3.13
- git
- (Khuyến nghị) conda/mamba hoặc venv để tạo môi trường riêng

## Setup

```bash
# 1. Fork & clone
git clone https://github.com/YOUR_USERNAME/app-free-api-information-retrieval
cd app-free-api-information-retrieval

# 2. Tạo virtual environment
python3 -m venv venv && source venv/bin/activate

# 3. Cài đặt dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Chạy test để xác nhận mọi thứ hoạt động
pytest

# 5. Cài đặt pre-commit hooks (tự động chạy lint trước mỗi commit)
pip install pre-commit
pre-commit install
```

## Branching Strategy

```
main          ← code đã merge, luôn ổn định
├── feature/<mô-tả>   ← tính năng mới
├── fix/<mô-tả>       ← sửa bug
└── refactor/<mô-tả>  ← cải thiện code không đổi behavior
```

- Branch từ `main`, PR vào `main`.
- Tên branch rõ ràng: `feature/add-gemini-provider`, `fix/health-check-timeout`.

## Coding Standards

### Code style
- **Ruff** dùng cho linting và formatting — chạy tự động qua pre-commit.
- Target Python 3.10 (không dùng syntax mới hơn mà không có fallback).
- Type hints ở mức **"pyright strict"** — càng rõ ràng càng tốt.

```bash
# Kiểm tra tất cả:
ruff check src/ tests/
ruff format src/ tests/
mypy src/  # type checking
```

### Naming conventions
- Module/package: `snake_case` (VD: `discovery/live.py`)
- Class/Type: `PascalCase` (VD: `ProviderStatus`)
- Function/method: `snake_case` (VD: `verify_provider`)
- Constant: `SCREAMING_SNAKE_CASE` (VD: `MAX_CONCURRENCY`)

### Commit Message Format
Dùng [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <mô tả ngắn>

VD:
feat(discovery): thêm provider mới Gemini
fix(cli): sửa exit code khi provider inactive
docs(readme): thêm troubleshooting section
refactor(checker): tách retry logic thành helper riêng
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`

## Pull Request Process

1. **Tạo PR** với mô tả rõ: problem → solution → testing.
2. **Tất cả CI phải xanh** trước khi merge:
   - `ruff check` (lint)
   - `ruff format --check` (format)
   - `pytest --cov=src` (test, coverage ≥ 90%)
   - `python run.py list` (smoke test)
3. **Ít nhất 1 reviewer** approve trước khi merge.
4. **Squash merge** — mỗi PR = 1 commit trên main.

## Testing

### Viết test mới
- Mỗi function/module mới phải có unit test tương ứng trong `tests/`.
- Mock network calls — không gọi API thật trong test.
- Đặt tên test rõ ràng: `test_<function>_<scenario>_<expected>`.

```python
# Ví dụ:
def test_verify_provider_retries_on_timeout(sample_provider, monkeypatch):
    ...

def test_extract_json_handles_brace_in_string():
    ...
```

### Running tests

```bash
# Tất cả tests
pytest

# Một file
pytest tests/test_cli.py -v

# Với coverage
pytest --cov=src --cov-report=term-missing

# Chỉ tests liên quan đến thay đổi (ví dụ discovery module)
pytest tests/test_discovery.py tests/test_live.py tests/test_ai_agent.py
```

## Documentation

- Public API cần docstring (Google style).
- README cập nhật nếu thêm command mới hoặc thay đổi cách dùng.
- CHANGELOG.md thêm entry cho mỗi PR (format Keep a Changelog).

## Questions?

Tạo GitHub Discussion hoặc open issue với label `question`.
