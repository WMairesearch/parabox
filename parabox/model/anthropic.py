"""Stateless Anthropic Messages access, translated to the session tool-call shape.

Native content blocks travel with their assistant message, so thinking blocks and
their signatures are returned unchanged with the tool results that follow them.
"""
from __future__ import annotations

import copy
import http.client
import json
import time
import urllib.error
import urllib.request

API_VERSION = "2023-06-01"


def _user(blocks: list[dict], content) -> None:
    # Messages rejects empty text blocks.
    if isinstance(content, list):
        blocks.extend(copy.deepcopy(content))
    elif content:
        blocks.append({"type": "text", "text": content})


def to_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    system, turns = [], []

    def turn(role: str) -> list[dict]:
        if not turns or turns[-1]["role"] != role:
            turns.append({"role": role, "content": []})
        return turns[-1]["content"]

    for message in messages:
        role = message.get("role")
        if role == "system":
            system.append(message.get("content") or "")
        elif role == "tool":
            result = {"type": "tool_result", "tool_use_id": message["tool_call_id"]}
            if message.get("content"):
                result["content"] = message["content"]
            turn("user").append(result)
        elif role == "assistant" and "anthropic_content" in message:
            turns.append({"role": "assistant", "content": copy.deepcopy(message["anthropic_content"])})
        elif role == "assistant":
            blocks = [{"type": "text", "text": message["content"]}] if message.get("content") else []
            for call in message.get("tool_calls") or []:
                function = call["function"]
                arguments = function.get("arguments") or "{}"
                blocks.append({"type": "tool_use", "id": call["id"], "name": function["name"],
                               "input": json.loads(arguments) if isinstance(arguments, str) else arguments})
            if blocks:
                turn("assistant").extend(blocks)
        else:
            _user(turn("user"), message.get("content"))
    return "\n\n".join(item for item in system if item), turns


def from_response(parsed: dict) -> dict:
    if parsed.get("type") == "error":
        raise RuntimeError("model response failed: " + json.dumps(parsed.get("error")))
    content = parsed["content"]
    texts, thoughts, calls = [], [], []
    for block in content:
        if block.get("type") == "text":
            texts.append(block["text"])
        elif block.get("type") == "thinking" and block.get("thinking"):
            thoughts.append(block["thinking"])
        elif block.get("type") == "tool_use":
            calls.append({"id": block["id"], "type": "function",
                          "function": {"name": block["name"],
                                       "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False)}})
    return {"role": "assistant", "content": "\n".join(texts), "reasoning_content": "\n".join(thoughts),
            "tool_calls": calls, "anthropic_content": copy.deepcopy(content)}


def _declarations(tools: list[dict]) -> list[dict]:
    return [{"name": item["function"]["name"], "description": item["function"].get("description") or "",
             "input_schema": copy.deepcopy(item["function"].get("parameters")
                                           or {"type": "object", "properties": {}})} for item in tools]


def complete(config: dict, key: str, messages: list[dict], *, tools=None,
             max_tokens: int = 32768, timeout: int = 360, thinking: bool = True):
    body = copy.deepcopy(config.get("request_body") or {})
    for name in ("messages", "system", "tools", "tool_choice", "model"):
        if name in body:
            raise ValueError(f"request_body cannot override {name}; session inputs are supplied by the runner")
    if not thinking:
        body["thinking"] = {"type": "disabled"}
        body.pop("output_config", None)
    body.setdefault("max_tokens", max_tokens)
    system, turns = to_messages(messages)
    payload = {**body, "model": config["model"], "messages": turns}
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = _declarations(tools)
        payload["tool_choice"] = {"type": "auto"}
    url = config["base_url"].rstrip("/") + "/messages"
    data = json.dumps(payload).encode()
    last = None
    for attempt in range(4):
        request = urllib.request.Request(
            url, data=data, method="POST",
            headers={"x-api-key": key, "anthropic-version": API_VERSION,
                     "Content-Type": "application/json", "User-Agent": "parabox/0.2.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read())
            return from_response(parsed), parsed
        except urllib.error.HTTPError as error:
            last = f"HTTP {error.code}: {error.read().decode('utf-8', errors='replace')[:1500]}"
            if error.code not in (429, 500, 502, 503, 529):
                raise RuntimeError(last) from None
            time.sleep(5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError,
                http.client.IncompleteRead) as error:
            last = error
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"model request failed: {last}")
