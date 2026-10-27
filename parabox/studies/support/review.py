"""Blind two-pass labelling of participant text.

Each pass sees the packets in its own shuffled order under neutral ids. Neither pass is
told the arm, the chain, or the generation. A label that cites a quote not found in the
text it refers to is set to false.
"""
from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path

from parabox.model import Client
from parabox.util import read, save, sha256

REVIEW_SEED = 2026092613
CONCURRENCY = 6
RETRY_NOTE = "Return one JSON object and nothing else."


def extract_json(content: str) -> dict:
    start = content.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for index in range(start, len(content)):
            char = content[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(content[start:index + 1])
                    except json.JSONDecodeError:
                        break
        start = content.find("{", start + 1)
    raise ValueError("no JSON object")


def quote_ok(quote: str, source: str, required: bool) -> bool:
    if not required:
        return quote == "" or quote in source
    return bool(quote) and quote in source


def shuffled(raw: list[dict], seed: int) -> tuple[list[dict], list[dict]]:
    """raw items carry `key` (hidden) and `packet` (shown). Returns packets and the id key."""
    order = list(raw)
    random.Random(seed).shuffle(order)
    packets, key = [], []
    for index, item in enumerate(order):
        identifier = f"p{index:04d}"
        packets.append({"id": identifier, **item["packet"]})
        key.append({"id": identifier, **item["key"]})
    return packets, key


def run_pass(folder: Path, name: str, raw: list[dict], manual: str, parse, client: Client, seed: int) -> None:
    packets, key = shuffled(raw, seed)
    save(folder / f"{name}-key.json", key)
    out = folder / name
    out.mkdir(parents=True, exist_ok=True)
    base = [{"role": "system", "content": manual}]

    async def one(packet, sem):
        async with sem:
            shown = {k: v for k, v in packet.items() if k != "id"}
            user = {"role": "user", "content": json.dumps(shown, ensure_ascii=False)}
            content = ""
            try:
                content = await asyncio.to_thread(client.text, base + [user])
                try:
                    label = parse(content, packet)
                except ValueError:
                    content = await asyncio.to_thread(client.text, base + [user, {"role": "user", "content": RETRY_NOTE}], thinking=False)
                    label = parse(content, packet)
                    label["retry"] = True
            except Exception as exc:
                (out / f"{packet['id']}.err").write_text(f"{exc}\n\n{content}")
                print(name, packet["id"], "ERROR", exc, flush=True)
                return
            save(out / f"{packet['id']}.json", label)

    async def main():
        sem = asyncio.Semaphore(CONCURRENCY)
        pending = [p for p in packets if not (out / f"{p['id']}.json").exists()]
        await asyncio.gather(*(one(p, sem) for p in pending))

    asyncio.run(main())
    missing = [p["id"] for p in packets if not (out / f"{p['id']}.json").exists()]
    if missing:
        raise SystemExit(f"review pass {name} is missing {len(missing)} labels")


def review(folder: Path, raw: list[dict], manual: str, parse, client: Client | None = None, seed: int = REVIEW_SEED) -> None:
    client = client or Client()
    save(folder / "manual.json", {"sha256": sha256(manual), "text": manual, "seed": seed, "model": client.model,
                                  "retry": "A reply with no JSON object is sent once more with thinking disabled where the wire allows it."})
    run_pass(folder, "a", raw, manual, parse, client, seed)
    run_pass(folder, "b", raw, manual, parse, client, seed + 1)


def labels(folder: Path, name: str, field: str) -> dict:
    """Map the hidden key `field` to the label of pass `name`."""
    return {item[field]: read(folder / name / f"{item['id']}.json") for item in read(folder / f"{name}-key.json")}
