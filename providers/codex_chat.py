"""Codex CLI Chat Provider - uses Codex OAuth tokens for OpenAI API calls."""

import json
import os
from pathlib import Path
from typing import Any

import litellm
from litellm import acompletion

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class CodexChatProvider(LLMProvider):
    """
    LLM provider that uses Codex CLI OAuth authentication.
    Reads tokens from ~/.codex/auth.json or ~/.codex/access_token
    and makes OpenAI API calls with Codex's permissions.
    """

    DEFAULT_MODEL = "o4-mini-2025-04-16"  # Codex's default model
    TOKEN_PATHS = [
        Path.home() / ".codex" / "auth.json",
        Path.home() / ".codex" / "access_token",
    ]

    def __init__(
        self,
        model: str | None = None,
        codex_home: Path | None = None,
        api_base: str | None = None,
    ):
        """
        Initialize Codex Chat Provider.
        
        Args:
            model: Model to use (defaults to Codex's o4-mini)
            codex_home: Path to .codex directory (default ~/.codex)
            api_base: Optional custom API base (defaults to OpenAI)
        """
        super().__init__(api_key=None, api_base=api_base)
        self.codex_home = codex_home or Path.home() / ".codex"
        self.model = model or self.DEFAULT_MODEL
        self._token_data: dict = {}
        self._access_token: str | None = None
        
        # Load and set the access token
        self._load_credentials()
        if self._access_token:
            os.environ["OPENAI_API_KEY"] = self._access_token
            litellm.api_base = api_base or "https://api.openai.com/v1"
        
        # Disable LiteLLM noise
        litellm.suppress_debug_info = True
    
    def _load_credentials(self) -> bool:
        """Load credentials from Codex CLI storage."""
        # Try auth.json first (full token data)
        auth_file = self.codex_home / "auth.json"
        if auth_file.exists():
            try:
                self._token_data = json.loads(auth_file.read_text())
                self._access_token = self._token_data.get("access_token")
                return True
            except (json.JSONDecodeError, IOError):
                pass
        
        # Fallback to access_token file
        token_file = self.codex_home / "access_token"
        if token_file.exists():
            try:
                self._access_token = token_file.read_text().strip()
                return True
            except IOError:
                pass
        
        return False
    
    @property
    def is_authenticated(self) -> bool:
        """Check if we have valid Codex credentials."""
        return bool(self._access_token)
    
    def get_status(self) -> dict:
        """Get authentication status info."""
        return {
            "authenticated": self.is_authenticated,
            "token_path": str(self.codex_home / "auth.json"),
            "access_token_path": str(self.codex_home / "access_token"),
            "model": self.model,
            "provider": "codex",
        }
    
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Send a chat completion request using Codex credentials.
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions.
            model: Model identifier (defaults to Codex o4-mini).
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
        
        Returns:
            LLMResponse with content and/or tool calls.
        """
        if not self.is_authenticated:
            return LLMResponse(
                content="⚠️ Codex not authenticated. Run `nanobot codex login` first.",
                finish_reason="error",
            )
        
        model = model or self.model
        
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        try:
            response = await acompletion(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            error_msg = str(e)
            # Check for specific error types
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                return LLMResponse(
                    content="⚠️ Codex authentication expired. Run `nanobot codex login` to refresh.",
                    finish_reason="error",
                )
            return LLMResponse(
                content=f"Error calling Codex: {error_msg}",
                finish_reason="error",
            )
    
    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse LiteLLM response into standard format."""
        choice = response.choices[0]
        message = choice.message
        
        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))
        
        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        
        return LLMResponse(
            content=None if tool_calls else message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )
    
    def get_default_model(self) -> str:
        """Get the default model."""
        return self.model
