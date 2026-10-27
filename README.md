# Free LLM Provider Discovery

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

Hoặc dùng Docker:

```bash
docker compose run app list
docker compose run app list --verify
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

## Cấu trúc project

```
src/
├── models.py                    # Data models (Provider, Model, ...)
├── config.py                    # Load .env (AI_PROVIDER_BASE_URL, AI_API_KEY, AI_MODEL)
├── discovery/
│   ├── __init__.py              # Gộp registry + helpers
│   ├── providers_part1.py       # Providers phổ biến (OpenRouter, Groq, ...)
│   ├── providers_part2.py       # Providers bổ sung (HF, DeepSeek, ...)
│   └── ai_agent.py              # AI Discovery Agent (gọi LLM tìm provider mới)
├── verification/
│   └── checker.py               # Async endpoint checker
├── aggregation/
│   └── aggregator.py            # Xuất JSON/YAML
└── cli/
    └── main.py                  # Click CLI: list / check / update / discover-ai
```

## Provider hiện có (15)

| Provider | Free tier | OpenAI-compatible | Ghi chú |
|----------|-----------|-------------------|---------|
| OpenRouter | ✅ (:free models) | ✅ | |
| Groq | ✅ | ✅ | |
| Google Gemini | ✅ | ❌ (custom) | |
| Mistral AI | ✅ (thí điểm) | ✅ | |
| Cohere | ✅ (trial key) | ❌ (custom) | |
| Together AI | ✅ | ✅ | |
| Hugging Face | ✅ | ❌ (custom) | serverless |
| Fireworks AI | ✅ | ✅ | |
| SiliconFlow | ⚠️ free + credits | ✅ | model nhỏ free |
| Anthropic | 💰 trial-only | ❌ (anthropic) | $5 credits |
| Perplexity | 💰 trial-only | ✅ | $5 credits |
| DeepSeek | 💰 trial-only | ✅ | 500M tokens |
| Novu.ai | ⚠️ unverified | ✅ | có thể đã chết |
| Leiku AI | ⚠️ unverified | ✅ | no-auth |
| OpenChat | ⚠️ unverified | ✅ | |

## Đóng góp

Muốn thêm provider mới? Sửa `src/discovery/providers_part2.py` và thêm entry
theo format `Provider(...)`. Sau đó chạy `update` để verify.

## Phát triển (Enterprise)

```bash
# Cài dev dependencies (pytest, ruff, ...)
./venv/bin/pip install -e ".[dev]"

# Chạy test suite (71 tests)
./venv/bin/python -m pytest tests/ --cov=src

# Lint + format
./venv/bin/ruff check src/ tests/
./venv/bin/ruff format src/ tests/

# Docker
docker compose run app list
```

CI tự chạy trên GitHub Actions: lint (ruff) → test matrix (Python 3.10–3.13,
coverage ≥ 85%) → CLI smoke test. Xem `.github/workflows/ci.yml`.

Lưu ý về dữ liệu registry:
- Provider tag `trial-only` = chỉ có credits khởi tạo, KHÔNG free lâu dài
  (`is_free=False` trên models).
- Provider tag `unverified` = chưa xác minh, endpoint có thể đã chết.
- Test `tests/test_discovery.py` đảm bảo nhất quán free/paid — nếu thêm provider
  sai tag, test sẽ fail.
