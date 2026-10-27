"""A local, deterministic BM25 index over message-board records.

No external dependency and no network: a session's search tool must give the same result
on replay. Tokenization is lowercase runs of word characters; scoring is Okapi BM25 with
the usual k1 and b. Ties break by the record's position in the index, so the order a study
assembles the index fixes the result.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

K1 = 1.5
B = 0.75
_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def document_text(record: dict) -> str:
    return f"{record.get('title', '')}\n{record.get('body', '')}"


@dataclass
class _Doc:
    record_id: str
    length: int
    frequencies: dict[str, int]


class Bm25Index:
    """Index the given records once; search returns record ids by descending score.

    Only documents with a positive score are returned, so a query that matches nothing
    yields an empty list rather than an arbitrary record.
    """

    def __init__(self, records: list[dict]):
        self.records = list(records)
        self._docs: list[_Doc] = []
        document_frequency: dict[str, int] = {}
        total_length = 0
        for record in self.records:
            tokens = tokenize(document_text(record))
            frequencies: dict[str, int] = {}
            for token in tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
            self._docs.append(_Doc(record["record_id"], len(tokens), frequencies))
            total_length += len(tokens)
            for token in frequencies:
                document_frequency[token] = document_frequency.get(token, 0) + 1
        count = len(self._docs)
        self._avg_length = (total_length / count) if count else 0.0
        self._idf = {
            token: math.log(1 + (count - freq + 0.5) / (freq + 0.5))
            for token, freq in document_frequency.items()
        }

    def _score(self, query_tokens: list[str], doc: _Doc) -> float:
        if not self._avg_length:
            return 0.0
        score = 0.0
        for token in query_tokens:
            frequency = doc.frequencies.get(token)
            if not frequency:
                continue
            idf = self._idf.get(token, 0.0)
            denominator = frequency + K1 * (1 - B + B * doc.length / self._avg_length)
            score += idf * frequency * (K1 + 1) / denominator
        return score

    def search(self, query: str, k: int = 5) -> list[str]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scored = []
        for index, doc in enumerate(self._docs):
            score = self._score(query_tokens, doc)
            if score > 0:
                scored.append((-score, index, doc.record_id))
        scored.sort()
        return [record_id for _, _, record_id in scored[:k]]
