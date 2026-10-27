"""
Registry phần 2: Providers bổ sung và ít phổ biến hơn
"""

from src.models import APIStyle, AuthType, Model, Provider, ProviderStatus

# ─── HUGGING FACE ───
HF_MODELS = [
    Model(
        id="mistralai/Mistral-7B-Instruct-v0.2",
        name="Mistral 7B v0.2",
        is_free=True,
        context_length=8192,
        supports_streaming=False,
    ),
    Model(
        id="meta-llama/Llama-2-7b-chat-hf",
        name="Llama 2 7B Chat",
        is_free=True,
        context_length=4096,
        supports_streaming=False,
    ),
    Model(
        id="Qwen/Qwen2-7B-Instruct",
        name="Qwen 2 7B",
        is_free=True,
        context_length=32768,
        supports_streaming=False,
    ),
    Model(
        id="google/gemma-2-2b-it",
        name="Gemma 2 2B IT",
        is_free=True,
        context_length=8192,
        supports_streaming=False,
    ),
]

HUGGINGFACE = Provider(
    name="Hugging Face Inference",
    base_url="https://api-inference.huggingface.co",
    website="https://huggingface.co/inference-api",
    description="Free tier cho Inference API. Model cần 'loaded' lần đầu (chờ ~30s).",
    models=HF_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.CUSTOM,
    auth_required=True,
    rate_limit="Free: rate limit theo model, không có SLA",
    tags=["open-source", "popular", "serverless"],
)

# ─── ANTHROPIC CLAUDE ───
ANTHROPIC_MODELS = [
    Model(
        id="claude-3-5-haiku-20241022",
        name="Claude 3.5 Haiku",
        is_free=False,
        context_length=200000,
        supports_streaming=True,
        description="Không miễn phí lâu dài — chỉ dùng $5 credits khởi tạo",
    ),
]

ANTHROPIC = Provider(
    name="Anthropic Claude API",
    base_url="https://api.anthropic.com/v1",
    website="https://console.anthropic.com",
    description="KHÔNG có free tier lâu dài. Chỉ $5 credits miễn phí cho tài khoản mới, "
    "hết credits cần thẻ tín dụng.",
    models=ANTHROPIC_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.ANTHROPIC,
    auth_required=True,
    rate_limit="$5 credits miễn phí cho tài khoản mới",
    tags=["free-credits", "popular", "trial-only"],
)

# ─── PERPLEXITY ───
PERPLEXITY_MODELS = [
    Model(
        id="sonar",
        name="Sonar",
        is_free=False,
        context_length=127072,
        supports_streaming=True,
        description="Không miễn phí lâu dài — chỉ dùng $5 credits khởi tạo",
    ),
    Model(
        id="sonar-pro",
        name="Sonar Pro",
        is_free=False,
        context_length=127072,
        supports_streaming=True,
    ),
]

PERPLEXITY = Provider(
    name="Perplexity API",
    base_url="https://api.perplexity.ai",
    website="https://perplexity.ai",
    description="KHÔNG có free tier lâu dài. Chỉ $5 credits miễn phí cho tài khoản mới.",
    models=PERPLEXITY_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="$5 credits miễn phí",
    tags=["search", "free-credits", "trial-only"],
)

# ─── FIREWORKS AI ───
FIREWORKS_MODELS = [
    Model(
        id="accounts/fireworks/models/llama-v3-8b-instruct",
        name="Llama 3 8B",
        is_free=True,
        context_length=8192,
        supports_streaming=True,
    ),
]

FIREWORKS = Provider(
    name="Fireworks AI",
    base_url="https://api.fireworks.ai/inference/v1",
    website="https://fireworks.ai",
    description="Nền tảng inference cho models mạnh. Free tier có giới hạn.",
    models=FIREWORKS_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="Free tier với token/day limit",
    tags=["fast-inference", "free-tier"],
)

# ─── SILICONFLOW ───
SILICONFLOW_MODELS = [
    Model(
        id="Qwen/Qwen2-7B-Instruct",
        name="Qwen 2 7B",
        is_free=True,
        context_length=32768,
        supports_streaming=True,
    ),
]

SILICONFLOW = Provider(
    name="SiliconFlow",
    base_url="https://api.siliconflow.cn/v1",
    website="https://siliconflow.cn",
    description="API nền tảng Trung Quốc, có một số model thực sự miễn phí (Qwen nhỏ, GLM). "
    "Cần đăng ký để nhận credits.",
    models=SILICONFLOW_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="Free tier cho model nhỏ, còn lại dùng credits",
    tags=["china", "free-tier", "openai-compatible"],
)

# ─── DEEPSEEK ───
DEEPSEEK_MODELS = [
    Model(
        id="deepseek-chat",
        name="DeepSeek Chat",
        is_free=False,
        context_length=64000,
        supports_streaming=True,
        description="Không miễn phí lâu dài — chỉ dùng 500M tokens khởi tạo",
    ),
    Model(
        id="deepseek-coder",
        name="DeepSeek Coder",
        is_free=False,
        context_length=16384,
        supports_streaming=True,
    ),
]

DEEPSEEK = Provider(
    name="DeepSeek API",
    base_url="https://api.deepseek.com/v1",
    website="https://platform.deepseek.com",
    description="KHÔNG có free tier lâu dài. Rất rẻ, tặng 500M tokens cho tài khoản mới.",
    models=DEEPSEEK_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="New users: 500M tokens miễn phí ban đầu",
    tags=["china", "free-credits", "openai-compatible", "coder", "trial-only"],
)

# ─── OLLAMA (Local) ───
OLLAMA_MODELS = [
    Model(
        id="llama3.2:latest",
        name="Llama 3.2 Latest",
        is_free=True,
        context_length=131072,
        supports_streaming=True,
    ),
    Model(
        id="qwen2.5:latest",
        name="Qwen 2.5 Latest",
        is_free=True,
        context_length=32768,
        supports_streaming=True,
    ),
    Model(
        id="mistral:latest",
        name="Mistral Latest",
        is_free=True,
        context_length=32768,
        supports_streaming=True,
    ),
]

OLLAMA = Provider(
    name="Ollama",
    base_url="http://localhost:11434/v1",
    website="https://ollama.com",
    description="Local LLM inference. Chạy hoàn toàn trên máy, không cần internet, không API key.",
    models=OLLAMA_MODELS,
    status=ProviderStatus.UNKNOWN,
    auth_type=AuthType.NONE,
    api_style=APIStyle.OPENAI,
    auth_required=False,
    rate_limit="Không giới hạn (chạy local)",
    tags=["local", "no-auth", "open-source"],
)

# ─── GIGACHAT (Russia) ───
GIGACHAT_MODELS = [
    Model(
        id="GigaChat",
        name="GigaChat",
        is_free=True,
        context_length=8192,
        supports_streaming=True,
    ),
    Model(
        id="GigaChat-Pro",
        name="GigaChat Pro",
        is_free=False,
        context_length=32768,
        supports_streaming=True,
    ),
]

GIGACHAT = Provider(
    name="GigaChat",
    base_url="https://gigachat.devices.sberbank.ru/api/v1",
    website="https://gigachat.ai",
    description="LLM của Sberbank (Nga), có free tier với giới hạn. Cần đăng ký tài khoản Sber ID.",
    models=GIGACHAT_MODELS,
    status=ProviderStatus.UNKNOWN,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.CUSTOM,
    auth_required=True,
    rate_limit="Free tier: 100 req/ngày sau khi đăng ký",
    tags=["russia", "free-tier"],
)

# ─── YANDEX GPT (Russia) ───
YANDEX_MODELS = [
    Model(
        id="yandexgpt-lite",
        name="YandexGPT Lite",
        is_free=True,
        context_length=8192,
        supports_streaming=True,
    ),
    Model(
        id="yandexgpt",
        name="YandexGPT",
        is_free=False,
        context_length=32000,
        supports_streaming=True,
    ),
]

YANDEX = Provider(
    name="Yandex Cloud",
    base_url="https://llm.api.cloud.yandex.net/foundationModels/v1",
    website="https://cloud.yandex.com/en/docs/llm/",
    description="Yandex LLM API. Có free tier giới hạn (Lite model). Cần Yandex Cloud account.",
    models=YANDEX_MODELS,
    status=ProviderStatus.UNKNOWN,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.CUSTOM,
    auth_required=True,
    rate_limit="Free tier: 5K tokens/phút, 50K tokens/ngày (Lite model)",
    tags=["russia", "free-tier"],
)

KNOWN_PROVIDERS_PART2: list[Provider] = [
    HUGGINGFACE,
    ANTHROPIC,
    PERPLEXITY,
    FIREWORKS,
    SILICONFLOW,
    DEEPSEEK,
    OLLAMA,
    GIGACHAT,
    YANDEX,
]
