"""
Registry phần 1: Các provider phổ biến nhất (đã xác minh)
"""

from typing import List
from src.models import Provider, Model, ProviderStatus, AuthType, APIStyle


# ─── OPENROUTER ───
OPENROUTER_MODELS = [
    Model(id="openchat/openchat-7b", name="OpenChat 7B", is_free=True,
          context_length=8192, supports_streaming=True),
    Model(id="mistralai/mistral-7b-instruct", name="Mistral 7B Instruct", is_free=True,
          context_length=8192, supports_streaming=True),
    Model(id="meta-llama/llama-2-13b-chat", name="Llama 2 13B Chat", is_free=True,
          context_length=4096, supports_streaming=True),
    Model(id="01-ai/yi-6b-chat", name="Yi 6B Chat", is_free=True,
          context_length=4096, supports_streaming=True),
    Model(id="openrouter/auto", name="Auto (Best Free)", is_free=True,
          context_length=128000, supports_streaming=True,
          description="Tự động chọn model miễn phí tốt nhất"),
    Model(id="qwen/qwen-14b-chat", name="Qwen 14B Chat", is_free=True,
          context_length=8192, supports_streaming=True),
    Model(id="deepseek/deepseek-67b-chat", name="DeepSeek 67B Chat", is_free=True,
          context_length=16384, supports_streaming=True),
    Model(id="nousresearch/nous-hermes-llama2-13b", name="Nous Hermes Llama2 13B", is_free=True,
          context_length=4096, supports_streaming=True),
]

OPENROUTER = Provider(
    name="OpenRouter",
    base_url="https://openrouter.ai/api/v1",
    website="https://openrouter.ai",
    description="Aggregator nhiều LLM. Nhiều model có tag ':free' dùng không mất phí.",
    models=OPENROUTER_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="200 req/ngày (free, không card); 1000 req/ngày (có card $10+)",
    tags=["aggregation", "multi-model", "popular", "free-tier"]
)

# ─── GROQ ───
# Lưu ý: Groq đã ngừng một số model cũ (mixtral-8x7b-32768, gemma2-9b-it).
# Danh sách này cần cập nhật định kỳ bằng lệnh: python run.py update
GROQ_MODELS = [
    Model(id="llama-3.1-8b-instant", name="Llama 3.1 8B Instant", is_free=True,
          context_length=131072, supports_streaming=True,
          description="Model chính free tier của Groq"),
    Model(id="llama-3.3-70b-versatile", name="Llama 3.3 70B Versatile", is_free=True,
          context_length=131072, supports_streaming=True),
    Model(id="gemma2-9b-it", name="Gemma 2 9B IT", is_free=True,
          context_length=8192, supports_streaming=True),
    Model(id="llama3-groq-70b-8192-tool-use-preview", name="Llama3 70B Tool Use", is_free=True,
          context_length=8192, supports_streaming=True),
]

GROQ = Provider(
    name="Groq",
    base_url="https://api.groq.com/openai/v1",
    website="https://console.groq.com",
    description="Inference cực nhanh trên LPU. Free tier hào phóng, tương thích OpenAI SDK.",
    models=GROQ_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="~30 req/phút, 14.400 req/ngày (free)",
    tags=["fast-inference", "free-tier", "openai-compatible"]
)

# ─── GOOGLE GEMINI ───
GEMINI_MODELS = [
    Model(id="gemini-1.5-flash", name="Gemini 1.5 Flash", is_free=True,
          context_length=1048576, supports_streaming=True),
    Model(id="gemini-1.5-flash-8b", name="Gemini 1.5 Flash 8B", is_free=True,
          context_length=1048576, supports_streaming=True),
    Model(id="gemini-1.5-pro", name="Gemini 1.5 Pro", is_free=True,
          context_length=2097152, supports_streaming=True),
    Model(id="gemini-1.0-pro", name="Gemini 1.0 Pro", is_free=True,
          context_length=32768, supports_streaming=True),
]

GOOGLE_GEMINI = Provider(
    name="Google Gemini API",
    base_url="https://generativelanguage.googleapis.com/v1beta",
    website="https://ai.google.dev",
    description="Free tier hào phóng của Google. Key lấy miễn phí tại AI Studio.",
    models=GEMINI_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.CUSTOM,
    auth_required=True,
    rate_limit="15 req/phút, 1500 req/ngày (free tier Gemini 1.5 Flash)",
    tags=["free-tier", "popular", "long-context"]
)

# ─── MISTRAL AI ───
MISTRAL_MODELS = [
    Model(id="open-mistral-7b", name="Mistral 7B", is_free=True,
          context_length=32768, supports_streaming=True),
    Model(id="open-mixtral-8x7b", name="Mixtral 8x7B", is_free=True,
          context_length=32768, supports_streaming=True),
    Model(id="open-mixtral-8x22b", name="Mixtral 8x22B", is_free=True,
          context_length=65536, supports_streaming=True),
    Model(id="mistral-small-latest", name="Mistral Small", is_free=True,
          context_length=32768, supports_streaming=True),
]

MISTRAL = Provider(
    name="Mistral AI",
    base_url="https://api.mistral.ai/v1",
    website="https://console.mistral.ai",
    description="La Plateforme có free tier (thí điểm), tương thích OpenAI SDK.",
    models=MISTRAL_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="1 req/giây, 500.000 token/phút, 1 tỷ token/tháng (free tier)",
    tags=["european", "free-tier", "openai-compatible"]
)

# ─── COHERE ───
COHERE_MODELS = [
    Model(id="command-r", name="Command R", is_free=True,
          context_length=128000, supports_streaming=True),
    Model(id="command-r-plus", name="Command R+", is_free=True,
          context_length=128000, supports_streaming=True),
    Model(id="command-r-08-2024", name="Command R 08-2024", is_free=True,
          context_length=128000, supports_streaming=True),
]

COHERE = Provider(
    name="Cohere",
    base_url="https://api.cohere.com/v2",
    website="https://dashboard.cohere.com",
    description="Trial key miễn phí cho mục đích phát triển và thử nghiệm.",
    models=COHERE_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.CUSTOM,
    auth_required=True,
    rate_limit="Trial: 20 req/phút, 1.000 req/tháng",
    tags=["trial-key", "rag"]
)

# ─── TOGETHER AI ───
TOGETHER_MODELS = [
    Model(id="meta-llama/Llama-3.2-3B-Instruct-Turbo", name="Llama 3.2 3B Turbo", is_free=True,
          context_length=131072, supports_streaming=True),
    Model(id="meta-llama/Meta-Llama-3-8B-Instruct-Turbo", name="Llama 3 8B Turbo", is_free=True,
          context_length=8192, supports_streaming=True),
    Model(id="mistralai/Mistral-7B-Instruct-v0.2", name="Mistral 7B Instruct v0.2", is_free=True,
          context_length=32768, supports_streaming=True),
]

TOGETHER_AI = Provider(
    name="Together AI",
    base_url="https://api.together.xyz/v1",
    website="https://api.together.ai",
    description="Có free tier giới hạn cho một số model open-source nhất định.",
    models=TOGETHER_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="Free tier: giới hạn theo model, cần đăng ký",
    tags=["open-source", "free-tier", "openai-compatible"]
)

KNOWN_PROVIDERS_PART1: List[Provider] = [
    OPENROUTER,
    GROQ,
    GOOGLE_GEMINI,
    MISTRAL,
    COHERE,
    TOGETHER_AI,
]
