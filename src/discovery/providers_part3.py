"""
Registry phần 3: Providers mới bổ sung (Cloudflare, Replicate, GitHub, Cerebras, SambaNova)
"""

from src.models import APIStyle, AuthType, Model, Provider, ProviderStatus

# ─── CLOUDFLARE WORKERS AI ───
# Endpoint OpenAI-compatible của Cloudflare: /client/v4/accounts/{account_id}/ai/v1
# Users thay {account_id} bằng account ID thật của mình.
CLOUDFLARE_MODELS = [
    Model(
        id="@cf/meta/llama-3.1-8b-instruct",
        name="Llama 3.1 8B Instruct",
        is_free=True,
        context_length=131072,
        supports_streaming=True,
        description="Model phổ biến nhất trên Workers AI",
    ),
    Model(
        id="@cf/meta/llama-3.2-3b-instruct",
        name="Llama 3.2 3B Instruct",
        is_free=True,
        context_length=131072,
        supports_streaming=True,
    ),
    Model(
        id="@cf/qwen/qwen1.5-7b-chat-awq",
        name="Qwen 1.5 7B Chat",
        is_free=True,
        context_length=32768,
        supports_streaming=True,
    ),
    Model(
        id="@cf/mistral/mistral-7b-instruct-v0.1",
        name="Mistral 7B Instruct v0.1",
        is_free=True,
        context_length=8192,
        supports_streaming=True,
    ),
]

CLOUDFLARE_WORKERS_AI = Provider(
    name="Cloudflare Workers AI",
    base_url="https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
    website="https://developers.cloudflare.com/workers-ai/",
    description="Inference ở edge Cloudflare. Free tier cấp 10K neurons/ngày. "
    "Thay {account_id} trong base_url bằng Account ID của bạn.",
    models=CLOUDFLARE_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="Free: 10.000 neurons/ngày",
    tags=["free-tier", "openai-compatible", "edge", "serverless"],
)

# ─── REPLICATE ───
# Không có free tier lâu dài — chỉ credits dùng thử ban đầu.
REPLICATE_MODELS = [
    Model(
        id="meta/meta-llama-3-8b-instruct",
        name="Llama 3 8B Instruct",
        is_free=False,
        context_length=8192,
        supports_streaming=True,
        description="Trả phí theo giây chạy — không free lâu dài",
    ),
    Model(
        id="mistralai/mixtral-8x7b-instruct-v0.1",
        name="Mixtral 8x7B Instruct",
        is_free=False,
        context_length=32768,
        supports_streaming=True,
    ),
]

REPLICATE = Provider(
    name="Replicate",
    base_url="https://api.replicate.com/v1",
    website="https://replicate.com",
    description="Chạy open-source model theo giây (pay-as-you-go). KHÔNG có free tier "
    "lâu dài — chỉ một lượng credits dùng thử nhỏ cho tài khoản mới.",
    models=REPLICATE_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.CUSTOM,
    auth_required=True,
    rate_limit="Trả phí theo giây chạy; giới hạn concurrency theo plan",
    tags=["open-source", "paid-only", "trial-only"],
)

# ─── GITHUB MODELS ───
GITHUB_MODELS_LIST = [
    Model(
        id="gpt-4o-mini",
        name="GPT-4o mini",
        is_free=True,
        context_length=128000,
        supports_streaming=True,
        description="Free qua GitHub PAT, rate limit theo tier tài khoản",
    ),
    Model(
        id="Meta-Llama-3.1-8B-Instruct",
        name="Llama 3.1 8B Instruct",
        is_free=True,
        context_length=131072,
        supports_streaming=True,
    ),
    Model(
        id="Phi-3.5-mini-instruct",
        name="Phi 3.5 Mini",
        is_free=True,
        context_length=131072,
        supports_streaming=True,
    ),
]

GITHUB_MODELS = Provider(
    name="GitHub Models",
    base_url="https://models.inference.ai.azure.com",
    website="https://github.com/marketplace/models",
    description="Dùng thử các model frontier MIỄN PHÍ bằng GitHub Personal Access Token. "
    "Rate limit theo tier tài khoản (free/paid Copilot).",
    models=GITHUB_MODELS_LIST,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="Free tier: giới hạn req/ngày + tokens/request theo tier PAT",
    tags=["free-tier", "openai-compatible", "github", "multi-model"],
)

# ─── CEREBRAS ───
CEREBRAS_MODELS = [
    Model(
        id="llama3.1-8b",
        name="Llama 3.1 8B",
        is_free=True,
        context_length=8192,
        supports_streaming=True,
        description="Inference siêu nhanh trên wafer-scale engine",
    ),
    Model(
        id="llama-3.3-70b",
        name="Llama 3.3 70B",
        is_free=True,
        context_length=8192,
        supports_streaming=True,
    ),
]

CEREBRAS = Provider(
    name="Cerebras",
    base_url="https://api.cerebras.ai/v1",
    website="https://cloud.cerebras.ai",
    description="Inference nhanh nhất thị trường (WSE hardware). Free tier hào phóng "
    "cho developer, tương thích OpenAI SDK.",
    models=CEREBRAS_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="Free tier: ~30 req/phút, 1M tokens/ngày",
    tags=["fast-inference", "free-tier", "openai-compatible"],
)

# ─── SAMBANOVA ───
SAMBANOVA_MODELS = [
    Model(
        id="Meta-Llama-3.1-8B-Instruct",
        name="Llama 3.1 8B Instruct",
        is_free=True,
        context_length=16384,
        supports_streaming=True,
    ),
    Model(
        id="Meta-Llama-3.3-70B-Instruct",
        name="Llama 3.3 70B Instruct",
        is_free=True,
        context_length=131072,
        supports_streaming=True,
    ),
]

SAMBANOVA = Provider(
    name="SambaNova",
    base_url="https://api.sambanova.ai/v1",
    website="https://cloud.sambanova.ai",
    description="Inference tốc độ cao trên custom RDU chip. Có free tier giới hạn, "
    "tương thích OpenAI SDK.",
    models=SAMBANOVA_MODELS,
    status=ProviderStatus.ACTIVE,
    auth_type=AuthType.API_KEY,
    api_style=APIStyle.OPENAI,
    auth_required=True,
    rate_limit="Free tier: giới hạn req/phút theo model",
    tags=["fast-inference", "free-tier", "openai-compatible"],
)

KNOWN_PROVIDERS_PART3: list[Provider] = [
    CLOUDFLARE_WORKERS_AI,
    REPLICATE,
    GITHUB_MODELS,
    CEREBRAS,
    SAMBANOVA,
]
