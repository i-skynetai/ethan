"""Router model — the reasoning the ROUTER does, not a KB. Provider-pluggable. v0.1: OpenAI. Anthropic later = new function."""
import json, os
from .util import http_json


def ask(messages, json_schema=None):
    """One LLM call. messages = [{role, content}]. With json_schema, returns parsed JSON."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set — fill it in .env")
    # no temperature: reasoning-family models accept only the default
    body = {"model": os.environ.get("OPENAI_MODEL", "gpt-5-mini"), "messages": messages}
    if json_schema:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "out", "schema": json_schema, "strict": True}}
    out = http_json("https://api.openai.com/v1/chat/completions", "POST", body,
                    {"Authorization": f"Bearer {key}"}, timeout=120)
    text = out["choices"][0]["message"]["content"]
    return json.loads(text) if json_schema else text
