"""Exercise the Anthropic provider over loopback HTTP; no hosted-model requests."""

import copy
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from parabox.benchmark.ternary.episode import truncated_response
from parabox.benchmark.ternary.runtime.base import Client as TernaryClient
from parabox.model import Client, assistant_message
from parabox.tasks.code.task import CodeTask


def tool_use(name, arguments, suffix="1"):
    return {"type": "tool_use", "id": "toolu_" + suffix, "name": name, "input": arguments}


def thinking(suffix="1", text="Plan."):
    return {"type": "thinking", "thinking": text, "signature": "sig-" + suffix}


def response(*content, suffix="1", stop_reason="tool_use"):
    return {"id": "msg_" + suffix, "type": "message", "role": "assistant",
            "model": "claude-opus-5-5", "content": list(content), "stop_reason": stop_reason,
            "usage": {"input_tokens": 100, "output_tokens": 20}}


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        self.requests = []
        self.replies = []


class FixtureHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append({"path": self.path, "body": body, "headers": {key.lower(): value for key, value in self.headers.items()}})
        status, value = self.server.replies.pop(0) if self.server.replies else (
            200, response({"type": "text", "text": "ok"}, stop_reason="end_turn"))
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


class AnthropicTest(unittest.TestCase):
    def setUp(self):
        self.server = FixtureServer()
        worker = threading.Thread(target=self.server.serve_forever,
                                  kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(worker.join)
        self.addCleanup(self.server.shutdown)
        env = patch.dict(os.environ, {"PARABOX_TEST_API_KEY": "fixture-key"})
        env.start()
        self.addCleanup(env.stop)
        self.config = {"wire": "anthropic", "model": "claude-opus-5-5",
                       "base_url": f"http://127.0.0.1:{self.server.server_port}/v1/",
                       "api_key_env": "PARABOX_TEST_API_KEY",
                       "request_body": {"thinking": {"type": "adaptive", "display": "summarized"},
                                        "output_config": {"effort": "high"}, "max_tokens": 4096}}
        self.client = Client(self.config)
        self.task = CodeTask()
        self.messages = [{"role": "system", "content": self.task.system(integrity="plain", shared=False)},
                         {"role": "user", "content": self.task.task(shared=False)}]

    def reply(self, value, status=200):
        self.server.replies.append((status, value))

    def test_routes_to_messages_preserving_prompts_tools_and_raw_response(self):
        tools = self.task.tools(shared=False)
        before = copy.deepcopy((self.messages, tools, self.config))
        raw = response(thinking(), tool_use("list_dir", {}))
        self.reply(raw)
        message, saved = self.client.complete(self.messages, tools=tools)
        request = self.server.requests[0]
        self.assertEqual(request["path"], "/v1/messages")
        self.assertEqual(request["headers"]["x-api-key"], "fixture-key")
        self.assertEqual(request["headers"]["anthropic-version"], "2023-06-01")
        self.assertNotIn("authorization", request["headers"])
        body = request["body"]
        self.assertEqual(body["model"], "claude-opus-5-5")
        self.assertEqual(body["system"], self.messages[0]["content"])
        self.assertEqual(body["messages"], [{"role": "user", "content": [
            {"type": "text", "text": self.messages[1]["content"]}]}])
        self.assertEqual(body["thinking"], {"type": "adaptive", "display": "summarized"})
        self.assertEqual(body["output_config"], {"effort": "high"})
        self.assertEqual(body["max_tokens"], 4096)
        self.assertEqual(body["tool_choice"], {"type": "auto"})
        for original, declaration in zip(tools, body["tools"], strict=True):
            self.assertEqual(declaration["name"], original["function"]["name"])
            self.assertEqual(declaration["input_schema"], original["function"]["parameters"])
        self.assertEqual(message["tool_calls"], [{"id": "toolu_1", "type": "function",
                                                  "function": {"name": "list_dir", "arguments": "{}"}}])
        self.assertEqual(message["reasoning_content"], "Plan.")
        self.assertEqual(saved, raw)
        self.assertEqual((self.messages, tools, self.config), before)

    def test_thinking_signatures_and_tool_results_return_unchanged(self):
        first = response(thinking("a"), {"type": "text", "text": "Listing."},
                         tool_use("list_dir", {}, "a"), tool_use("read_file", {"path": "x"}, "b"))
        self.reply(first)
        message, _ = self.client.complete(self.messages, tools=self.task.tools(shared=False))
        self.messages.extend([assistant_message(message),
                              {"role": "tool", "tool_call_id": "toolu_a", "content": "listing"},
                              {"role": "tool", "tool_call_id": "toolu_b", "content": ""},
                              {"role": "user", "content": "Continue."}])
        self.client.complete(self.messages, tools=self.task.tools(shared=False))
        turns = self.server.requests[1]["body"]["messages"]
        self.assertEqual(turns[1], {"role": "assistant", "content": first["content"]})
        self.assertEqual(turns[2], {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_a", "content": "listing"},
            {"type": "tool_result", "tool_use_id": "toolu_b"},
            {"type": "text", "text": "Continue."}]})
        self.assertEqual(len(turns), 3)

    def test_converts_existing_chat_style_history(self):
        messages = self.messages + [
            {"role": "assistant", "content": "Looking.", "tool_calls": [{"id": "call_old", "type": "function",
             "function": {"name": "read_file", "arguments": '{"path": "a"}'}}]},
            {"role": "tool", "tool_call_id": "call_old", "content": "files"},
        ]
        self.client.complete(messages)
        self.assertEqual(self.server.requests[0]["body"]["messages"][1:], [
            {"role": "assistant", "content": [
                {"type": "text", "text": "Looking."},
                {"type": "tool_use", "id": "call_old", "name": "read_file", "input": {"path": "a"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_old", "content": "files"}]},
        ])

    def test_text_helper_disables_thinking(self):
        self.reply(response({"type": "text", "text": '{"answer": 1}'}, stop_reason="end_turn"))
        self.assertEqual(self.client.text(self.messages, thinking=False), '{"answer": 1}')
        body = self.server.requests[0]["body"]
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertNotIn("output_config", body)
        self.assertNotIn("tools", body)

    def test_request_body_cannot_replace_inputs(self):
        for key in ("messages", "system", "tools", "tool_choice", "model"):
            with self.subTest(key=key):
                config = {**self.config, "request_body": {key: "override"}}
                with self.assertRaisesRegex(ValueError, key):
                    Client(config).complete(self.messages)
        self.assertEqual(self.server.requests, [])

    def test_transient_http_errors_retry_the_same_request(self):
        self.reply({"type": "error", "error": {"type": "overloaded_error"}}, status=529)
        self.reply({"type": "error", "error": {"type": "rate_limit_error"}}, status=429)
        raw = response(tool_use("finish", {"report": "done"}))
        self.reply(raw)
        with patch("time.sleep"):
            _, saved = self.client.complete(self.messages)
        self.assertEqual(saved, raw)
        self.assertEqual([item["body"] for item in self.server.requests], [self.server.requests[0]["body"]] * 3)

    def test_permanent_http_error_is_not_retried(self):
        self.reply({"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}, status=400)
        with self.assertRaisesRegex(RuntimeError, "HTTP 400.*bad"):
            self.client.complete(self.messages)
        self.assertEqual(len(self.server.requests), 1)

    def test_ternary_runtime_dispatches_and_detects_truncation(self):
        raw = response({"type": "text", "text": "partial"}, stop_reason="max_tokens")
        self.reply(raw)
        _, saved = TernaryClient(self.config).complete(self.messages)
        self.assertEqual(self.server.requests[0]["path"], "/v1/messages")
        self.assertTrue(truncated_response(saved))
        self.assertFalse(truncated_response(response(stop_reason="end_turn")))


if __name__ == "__main__":
    unittest.main()
