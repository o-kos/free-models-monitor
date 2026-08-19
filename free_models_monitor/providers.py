"""Provider adapters: fetch free-tier model catalogs.

Add a new provider by writing a fetch_<name>_free() -> (dict, error)
function below and registering it in PROVIDERS. monitor.py only calls
functions from here, it never talks to a provider API directly.
"""
import json
import urllib.error
import urllib.request

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
USER_AGENT = "free-models-monitor/1.0"

# Preference order for automatic fallback suggestions. Overridable via
# --fallback-chain-file (a JSON list, or {"fallback_chain": [...]}).
DEFAULT_FALLBACK_CHAIN = [
    "openrouter/qwen/qwen3-next-80b-a3b-instruct:free",
    "openrouter/openai/gpt-oss-120b:free",
    "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/nousresearch/hermes-3-llama-3.1-405b:free",
    "openrouter/qwen/qwen3-coder:free",
    "openrouter/moonshotai/kimi-k2:free",
    "openrouter/openai/gpt-oss-20b:free",
    "openrouter/meta-llama/llama-3.2-3b-instruct:free",
    "groq/llama-3.3-70b-versatile",
]

# Groq has no public "free tier" catalog endpoint, so this list is
# maintained by hand. Edit it if Groq changes its free lineup, or pass
# your own --fallback-chain-file if you only care about fallback order.
GROQ_FREE_MODELS = {
    "groq/llama-3.3-70b-versatile": {
        "name": "Llama 3.3 70B Versatile (Groq)",
        "context_length": 128000,
    },
    "groq/llama-3.1-8b-instant": {
        "name": "Llama 3.1 8B Instant (Groq)",
        "context_length": 128000,
    },
    "groq/gemma2-9b-it": {"name": "Gemma2 9B IT (Groq)", "context_length": 8192},
    "groq/mixtral-8x7b-32768": {"name": "Mixtral 8x7B (Groq)", "context_length": 32768},
}


def _is_free_price(value):
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


def fetch_openrouter_free(timeout=15):
    """Fetches OpenRouter's model catalog, keeps the ones priced at zero.

    Returns (dict, None) on success, keyed by the raw OpenRouter id (no
    prefix; monitor.py normalizes ids). Returns (None, error_str) on
    failure so callers can tell "zero free models" from "fetch failed".
    """
    req = urllib.request.Request(
        OPENROUTER_MODELS_URL, headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return None, f"OpenRouter fetch error: {e}"

    free = {}
    for m in payload.get("data", []):
        mid = m.get("id", "")
        pricing = m.get("pricing", {})
        if _is_free_price(pricing.get("prompt")) and _is_free_price(
            pricing.get("completion")
        ):
            free[mid] = {
                "name": m.get("name", mid),
                "context_length": m.get("context_length", 0) or 0,
            }
    return free, None


def fetch_groq_free():
    """Returns Groq's free model list (static, see GROQ_FREE_MODELS)."""
    return dict(GROQ_FREE_MODELS), None


PROVIDERS = {
    "openrouter": fetch_openrouter_free,
    "groq": fetch_groq_free,
}
