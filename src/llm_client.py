"""Model-agnostic LLM client supporting Groq, OpenAI, and Anthropic."""

import httpx
import json
import time
import os
import re
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    estimated_cost_usd: float


# Pricing per 1M tokens (input, output) — approximate
PRICING = {
    "groq": {"default": (0.0, 0.0)},  # Groq free tier
    "openai": {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        "default": (0.15, 0.60),
    },
    "anthropic": {
        "claude-sonnet-4-20250514": (3.00, 15.00),
        "claude-haiku-4-20250414": (0.80, 4.00),
        "default": (3.00, 15.00),
    },
}

# API base URLs
API_BASES = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
}


class LLMClient:
    """Unified LLM client. Supports Groq, OpenAI, and Anthropic.
    
    All three providers use similar chat completion APIs.
    Groq and OpenAI use the OpenAI-compatible format.
    Anthropic uses its own Messages API format.
    """
    
    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ):
        self.provider = provider or os.getenv("LLM_PROVIDER", "groq")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        if not self.api_key:
            raise ValueError(
                f"LLM API key not set. Set LLM_API_KEY in .env or pass api_key parameter."
            )
        
        self.api_base = API_BASES.get(self.provider)
        if not self.api_base:
            raise ValueError(f"Unknown LLM provider: {self.provider}. Use 'groq', 'openai', or 'anthropic'.")
    
    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD based on provider pricing."""
        provider_pricing = PRICING.get(self.provider, {})
        model_pricing = provider_pricing.get(self.model, provider_pricing.get("default", (0.0, 0.0)))
        input_cost = (input_tokens / 1_000_000) * model_pricing[0]
        output_cost = (output_tokens / 1_000_000) * model_pricing[1]
        return round(input_cost + output_cost, 6)
    
    def chat(self, system_prompt: str, user_message: str) -> LLMResponse:
        """Send a chat completion request and return structured response."""
        start_time = time.time()
        
        if self.provider == "anthropic":
            return self._chat_anthropic(system_prompt, user_message, start_time)
        else:
            # Groq and OpenAI use the same API format
            return self._chat_openai_compatible(system_prompt, user_message, start_time)
    
    def _chat_openai_compatible(self, system_prompt: str, user_message: str, start_time: float) -> LLMResponse:
        """Chat using OpenAI-compatible API (works for Groq and OpenAI)."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        
        max_retries = 5
        retry_delay = 2.0
        
        with httpx.Client(timeout=60.0) as client:
            for attempt in range(max_retries):
                resp = client.post(f"{self.api_base}/chat/completions", headers=headers, json=payload)
                if resp.status_code == 429:
                    wait_time = retry_delay
                    retry_header = resp.headers.get("retry-after")
                    if retry_header:
                        try:
                            wait_time = max(float(retry_header), 1.0)
                        except (ValueError, TypeError):
                            pass
                    else:
                        try:
                            err_data = resp.json()
                            msg = err_data.get("error", {}).get("message", "")
                            match = re.search(r"try again in (\d+\.?\d*)s", msg)
                            if match:
                                wait_time = max(float(match.group(1)) + 0.5, 1.0)
                        except Exception:
                            pass
                    print(f" (Rate limit: waiting {wait_time:.1f}s) ", end="", flush=True)
                    time.sleep(wait_time)
                    retry_delay *= 2
                    continue
                resp.raise_for_status()
                break
            else:
                resp.raise_for_status()
        
        data = resp.json()
        latency_ms = (time.time() - start_time) * 1000
        
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.model),
            provider=self.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency_ms, 1),
            estimated_cost_usd=self._estimate_cost(input_tokens, output_tokens),
        )
    
    def _chat_anthropic(self, system_prompt: str, user_message: str, start_time: float) -> LLMResponse:
        """Chat using Anthropic Messages API."""
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_message},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{self.api_base}/messages", headers=headers, json=payload)
            resp.raise_for_status()
        
        data = resp.json()
        latency_ms = (time.time() - start_time) * 1000
        
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block["text"]
        
        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            provider=self.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency_ms, 1),
            estimated_cost_usd=self._estimate_cost(input_tokens, output_tokens),
        )
