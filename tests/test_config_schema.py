from nanobot.config.schema import Config


def test_discord_defaults_present() -> None:
    cfg = Config()
    assert cfg.channels.discord.enabled is False
    assert cfg.channels.discord.gateway_url.startswith("wss://gateway.discord.gg/")
    assert cfg.channels.discord.intents == 37377


def test_qwen_uses_dashscope_provider() -> None:
    cfg = Config()
    cfg.agents.defaults.model = "qwen-max"
    cfg.providers.openrouter.api_key = "sk-or-v1-test"
    cfg.providers.dashscope.api_key = "dashscope-test"

    assert cfg.get_api_key(cfg.agents.defaults.model) == "dashscope-test"
    assert cfg.get_api_base(cfg.agents.defaults.model) is None


def test_kimi_uses_moonshot_defaults() -> None:
    cfg = Config()
    cfg.agents.defaults.model = "moonshotai/Kimi-K2.5"
    cfg.providers.moonshot.api_key = "moonshot-test"

    assert cfg.get_api_key(cfg.agents.defaults.model) == "moonshot-test"
    assert cfg.get_api_base(cfg.agents.defaults.model) == "https://api.moonshot.cn/v1"


def test_fallback_priority_starts_with_openrouter() -> None:
    cfg = Config()
    cfg.agents.defaults.model = "unknown-provider/model"
    cfg.providers.openrouter.api_key = "sk-or-v1-test"
    cfg.providers.together.api_key = "together-test"

    assert cfg.get_api_key(cfg.agents.defaults.model) == "sk-or-v1-test"
    assert cfg.get_api_base(cfg.agents.defaults.model) == "https://openrouter.ai/api/v1"
