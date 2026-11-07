"""Optional LLM tier (stdlib only). Providers: Groq (free tier, OpenAI-compatible), OpenAI, or Anthropic.

Selection:  REPOBRAIN_LLM_PROVIDER=groq|anthropic|openai  (default: groq if GROQ_API_KEY is set, else anthropic)
Model:      REPOBRAIN_MODEL                               (default per provider; check your provider's model list)
Used ONLY when policy.allow_llm is true AND the caller opts in, never on files with Shield findings, and
every result is test-gated and human-approved like any other change."""
import json
import os
import time
import urllib.error
import urllib.request

PROVIDERS = {
    "groq": {"key_env": "GROQ_API_KEY", "base": "https://api.groq.com/openai/v1",
             "model": "openai/gpt-oss-120b"},
    "anthropic": {"key_env": "ANTHROPIC_API_KEY", "base": "https://api.anthropic.com",
                  "model": "claude-sonnet-5-5"},
    "openai": {"key_env": "OPENAI_API_KEY", "base": "https://api.openai.com/v1",
               "model": "gpt-4o-mini"},
}
UA = "repobrain/0.2 (+local)"        # Groq sits behind Cloudflare, which can reject Python's default User-Agent


class LLMError(RuntimeError):
    pass


def provider():
    p = (os.environ.get("REPOBRAIN_LLM_PROVIDER") or os.environ.get("REPOBRAIN_LLM") or "").lower()
    if p in PROVIDERS:
        return p
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "anthropic"


def key_env():
    return PROVIDERS[provider()]["key_env"]


def available():
    return bool(os.environ.get(key_env()) or os.environ.get("REPOBRAIN_LLM_URL") or os.environ.get("REPOBRAIN_LLM_BASE_URL"))


def missing_key_hint():
    return f"{key_env()} not set (provider: {provider()})"


def describe():
    return {"provider": provider(), "model": os.environ.get("REPOBRAIN_MODEL", PROVIDERS[provider()]["model"]),
            "available": available(), "key_env": key_env()}


def _post(url, headers, body, retries=3):
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data, {"content-type": "application/json", "user-agent": UA, **headers})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 503) and attempt < retries:        # free tiers rate-limit: honour Retry-After
                try:
                    wait = float(e.headers.get("retry-after") or 0)
                except ValueError:
                    wait = 0
                time.sleep(min(max(wait, 2 ** attempt), 30))
                continue
            hint = {401: " - check the API key", 403: " - blocked or key lacks access", 404: " - model name not found for this provider",
                    429: " - free-tier rate limit hit, wait a minute or pick another model"}.get(e.code, "")
            raise LLMError(f"HTTP {e.code}{hint}: {detail}") from None
        except urllib.error.URLError as e:
            raise LLMError(f"network error: {e.reason}") from None


def ask(prompt, system="", max_tokens=None):
    p = provider()
    cfg = PROVIDERS[p]
    key = os.environ.get(cfg["key_env"])
    if not key and (os.environ.get("REPOBRAIN_LLM_URL") or os.environ.get("REPOBRAIN_LLM_BASE_URL")):
        key = "mock-key"
    if not key:
        raise LLMError(missing_key_hint())
    model = os.environ.get("REPOBRAIN_MODEL", cfg["model"])
    base = (os.environ.get("REPOBRAIN_LLM_URL") or os.environ.get("REPOBRAIN_LLM_BASE_URL") or cfg["base"]).rstrip("/")
    if p in ("groq", "openai"):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        data = _post(base + "/chat/completions", {"authorization": f"Bearer {key}"},
                     {"model": model, "messages": msgs, "temperature": 0.1,
                      "max_tokens": max_tokens or 4096})
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"unexpected response shape: {str(data)[:200]}") from None
    else:
        data = _post(base + "/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"},
                     {"model": model, "max_tokens": max_tokens or 2000, "system": system,
                      "messages": [{"role": "user", "content": prompt}]})
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if not text.strip():
        raise LLMError("model returned an empty reply (reasoning models may need a larger max_tokens)")
    return text
