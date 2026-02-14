"""Configuration schema using Pydantic."""

from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class WhatsAppConfig(BaseModel):
    """WhatsApp channel configuration."""
    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    allow_from: list[str] = Field(default_factory=list)  # Allowed phone numbers


class TelegramConfig(BaseModel):
    """Telegram channel configuration."""
    enabled: bool = False
    token: str = ""  # Bot token from @BotFather
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs or usernames
    proxy: str | None = None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"


class FeishuConfig(BaseModel):
    """Feishu/Lark channel configuration using WebSocket long connection."""
    enabled: bool = False
    app_id: str = ""  # App ID from Feishu Open Platform
    app_secret: str = ""  # App Secret from Feishu Open Platform
    encrypt_key: str = ""  # Encrypt Key for event subscription (optional)
    verification_token: str = ""  # Verification Token for event subscription (optional)
    allow_from: list[str] = Field(default_factory=list)  # Allowed user open_ids


class DiscordConfig(BaseModel):
    """Discord channel configuration."""
    enabled: bool = False
    token: str = ""  # Bot token from Discord Developer Portal
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377  # GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES + MESSAGE_CONTENT


class ChannelsConfig(BaseModel):
    """Configuration for chat channels."""
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)


class AgentDefaults(BaseModel):
    """Default agent configuration."""
    workspace: str = "~/.nanobot/workspace"
    model: str = "anthropic/claude-opus-4-5"
    max_tokens: int = 8192
    temperature: float = 0.7
    max_tool_iterations: int = 20


class AgentsConfig(BaseModel):
    """Agent configuration."""
    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(BaseModel):
    """LLM provider configuration."""
    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None


class ProvidersConfig(BaseModel):
    """Configuration for LLM providers."""
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    together: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)


class LiteLLMSettings(BaseModel):
    """LiteLLM runtime settings."""
    allowed_openai_params: list[str] = Field(default_factory=list)
    drop_params: bool | None = None
    use_litellm_proxy: bool = False


class GatewayConfig(BaseModel):
    """Gateway/server configuration."""
    host: str = "0.0.0.0"
    port: int = 18790


class WebSearchConfig(BaseModel):
    """Web search tool configuration."""
    api_key: str = ""  # Brave Search API key
    max_results: int = 5


class WebToolsConfig(BaseModel):
    """Web tools configuration."""
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(BaseModel):
    """Shell exec tool configuration."""
    timeout: int = 60
    restrict_to_workspace: bool = False  # If true, block commands accessing paths outside workspace


class ToolsConfig(BaseModel):
    """Tools configuration."""
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)


class Config(BaseSettings):
    """Root configuration for nanobot."""
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    litellm_settings: LiteLLMSettings = Field(default_factory=LiteLLMSettings)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    _GATEWAY_DEFAULTS = {
        "openrouter": "https://openrouter.ai/api/v1",
        "together": "https://api.together.xyz/v1",
        "moonshot": "https://api.moonshot.cn/v1",
        "aihubmix": "https://aihubmix.com/v1",
    }
    
    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base). Falls back to first available."""
        model_lower = (model or self.agents.defaults.model).lower()
        p = self.providers
        keyword_map = {
            "aihubmix": p.aihubmix,
            "openrouter": p.openrouter,
            "together": p.together,
            "deepseek": p.deepseek,
            "anthropic": p.anthropic,
            "claude": p.anthropic,
            "openai": p.openai,
            "gpt": p.openai,
            "gemini": p.gemini,
            "zhipu": p.zhipu,
            "glm": p.zhipu,
            "zai": p.zhipu,
            "dashscope": p.dashscope,
            "qwen": p.dashscope,
            "moonshot": p.moonshot,
            "kimi": p.moonshot,
            "groq": p.groq,
            "vllm": p.vllm,
        }
        for kw, provider in keyword_map.items():
            if kw in model_lower and provider.api_key:
                return provider

        all_providers = [
            p.openrouter,
            p.aihubmix,
            p.together,
            p.deepseek,
            p.anthropic,
            p.openai,
            p.gemini,
            p.zhipu,
            p.dashscope,
            p.moonshot,
            p.vllm,
            p.groq,
        ]
        return next((provider for provider in all_providers if provider.api_key), None)

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for model. Falls back to first available key."""
        provider = self.get_provider(model)
        return provider.api_key if provider else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """Get API base URL for model."""
        provider = self.get_provider(model)
        if provider and provider.api_base:
            return provider.api_base
        for name, default_url in self._GATEWAY_DEFAULTS.items():
            if provider is getattr(self.providers, name):
                return default_url
        if self.providers.vllm.api_base:
            return self.providers.vllm.api_base
        return None
    
    class Config:
        env_prefix = "NANOBOT_"
        env_nested_delimiter = "__"
