"""Vertex Gemini generateContent, translated to the chat tool-call shape."""
from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request


def _schema(parameters: dict) -> dict:
    schema = {key: value for key, value in parameters.items() if key != "additionalProperties"}
    properties = schema.get("properties") or {}
    schema["properties"] = {
        name: {key: value for key, value in spec.items() if key != "additionalProperties"}
        for name, spec in properties.items()
    }
    return schema


def _declarations(tools: list[dict]) -> list[dict]:
    return [{
        "name": item["function"]["name"],
        "description": item["function"].get("description") or "",
        "parameters": _schema(item["function"].get("parameters") or {"type": "object", "properties": {}}),
    } for item in tools]


def _tool_name(call_id: str, previous: dict) -> str:
    call = previous.get(call_id) or {}
    name = (call.get("function") or {}).get("name")
    if name:
        return name
    return call_id.split(":", 1)[0]


def to_contents(messages: list[dict]) -> tuple[str, list[dict]]:
    system = []
    contents = []
    names: dict[str, dict] = {}
    pending: list[dict] = []

    def flush() -> None:
        if pending:
            contents.append({"role": "user", "parts": list(pending)})
            pending.clear()

    for message in messages:
        role = message.get("role")
        if role == "system":
            system.append(message.get("content") or "")
            continue
        if role == "tool":
            pending.append({
                "functionResponse": {
                    "name": _tool_name(message.get("tool_call_id") or "", names),
                    "response": {"result": message.get("content") or ""},
                },
            })
            continue
        flush()
        if role == "assistant":
            parts = []
            text = message.get("content") or ""
            if text:
                parts.append({"text": text})
            for call in message.get("tool_calls") or []:
                names[call.get("id") or ""] = call
                arguments = (call.get("function") or {}).get("arguments") or "{}"
                try:
                    args = json.loads(arguments) if isinstance(arguments, str) else arguments
                except json.JSONDecodeError:
                    args = {}
                part = {
                    "functionCall": {
                        "name": (call.get("function") or {}).get("name"),
                        "args": args if isinstance(args, dict) else {},
                    },
                }
                if call.get("thoughtSignature"):
                    part["thoughtSignature"] = call["thoughtSignature"]
                parts.append(part)
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue
        contents.append({"role": "user", "parts": [{"text": message.get("content") or ""}]})
    flush()
    return "\n\n".join(item for item in system if item), contents


def from_response(parsed: dict) -> dict:
    candidate = parsed["candidates"][0]
    parts = (candidate.get("content") or {}).get("parts") or []
    thoughts = []
    texts = []
    calls = []
    for index, part in enumerate(parts):
        if part.get("thought") and part.get("text"):
            thoughts.append(part["text"])
            continue
        if part.get("text"):
            texts.append(part["text"])
        call = part.get("functionCall")
        if not call:
            continue
        name = call.get("name") or "tool"
        calls.append({
            "id": f"{name}:{index}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(call.get("args") or {}, ensure_ascii=False)},
            "thoughtSignature": part.get("thoughtSignature"),
        })
    return {
        "role": "assistant",
        "content": "\n".join(texts),
        "reasoning_content": "\n".join(thoughts),
        "tool_calls": calls,
    }


def complete(config: dict, key: str, messages: list[dict], *, tools=None, max_tokens: int = 32768, timeout: int = 360):
    system, contents = to_contents(messages)
    body = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingLevel": (config.get("request_body") or {}).get("thinking_level") or "HIGH"},
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = [{"functionDeclarations": _declarations(tools)}]
    url = config["base_url"].rstrip("/") + f"/{config['model']}:generateContent"
    data = json.dumps(body).encode()
    last = None
    for attempt in range(4):
        request = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read())
            return from_response(parsed), parsed
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:1500]
            last = f"HTTP {error.code}: {detail}"
            if error.code not in (429, 500, 502, 503):
                raise RuntimeError(last) from None
            time.sleep(5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError,
                http.client.IncompleteRead) as error:
            last = error
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"model request failed: {last}")
