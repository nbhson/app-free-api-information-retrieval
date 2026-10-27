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

# ─── NOvus AI ───
NOVUS_MODELS = [
    Model(
        id="nousresearch/hermes-3-llama-3.1-8b",
        name="Hermes 3 Llama 3.1 8B",
        is_free=True,
        context_length=131072,
        supports_streaming=True,
    ),
]

NOVUS = Provider(
    name="Novu.ai",
    base_url="https://api.novu.ai/v1",
    website="https://novu.ai",
    description="Open-source model API với free tier. ⚠️ CHƯA XÁC MINH — endpoint có thể đã chết.",
    models=NOVUS_MODELS,
    status=ProviderStatus.UNKNOWN,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="Free tier giới hạn",
    tags=["open-source", "free-tier", "unverified"],
)

# ─── LEIKU AI ───
LEIKU_MODELS = [
    Model(
        id="default",
        name="Default Model",
        is_free=True,
        context_length=8192,
        supports_streaming=True,
    ),
]

LEIKU = Provider(
    name="Leiku AI",
    base_url="https://api.leiku.io/v1",
    website="https://leiku.io",
    description="API miễn phí của cộng đồng AI Việt Nam. ⚠️ CHƯA XÁC MINH — endpoint có thể đã chết.",
    models=LEIKU_MODELS,
    status=ProviderStatus.UNKNOWN,
    auth_type=AuthType.NONE,
    api_style=APIStyle.OPENAI,
    auth_required=False,
    rate_limit="Không rõ",
    tags=["vietnam", "free", "no-auth", "unverified"],
)

# ─── OPENCHAT ───
OPENCHAT_MODELS = [
    Model(
        id="openchat-3.5-1210",
        name="OpenChat 3.5",
        is_free=True,
        context_length=8192,
        supports_streaming=True,
    ),
]

OPENCHAT = Provider(
    name="OpenChat",
    base_url="https://api.openchat.chat/v1",
    website="https://openchat.chat",
    description="Cung cấp model OpenChat miễn phí qua API. ⚠️ CHƯA XÁC MINH — endpoint có thể đã chết.",
    models=OPENCHAT_MODELS,
    status=ProviderStatus.UNKNOWN,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="Free tier với daily limit",
    tags=["open-source", "free-tier", "unverified"],
)

KNOWN_PROVIDERS_PART2: list[Provider] = [
    HUGGINGFACE,
    ANTHROPIC,
    PERPLEXITY,
    FIREWORKS,
    SILICONFLOW,
    DEEPSEEK,
    NOVUS,
    LEIKU,
    OPENCHAT,
]
