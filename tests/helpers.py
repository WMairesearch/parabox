from __future__ import annotations

import json


class FakeBox:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    def start(self):
        pass

    def stop(self):
        pass


def call(name, args, suffix="a"):
    return {"id": f"{name}-{suffix}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
