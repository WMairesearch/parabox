import unittest

from parabox.retrieval import Bm25Index, tokenize


def records():
    return [
        {"record_id": "record-0001", "title": "Collatz step", "body": "the collatz conjecture iterates collatz collatz"},
        {"record_id": "record-0002", "title": "Riemann", "body": "the riemann hypothesis concerns zeros"},
        {"record_id": "record-0003", "title": "Notes", "body": "local notation can shadow an identifier"},
    ]


class TokenizeTest(unittest.TestCase):
    def test_lowercase_word_runs(self):
        self.assertEqual(tokenize("Collatz_step: 3n+1!"), ["collatz", "step", "3n", "1"])


class Bm25Test(unittest.TestCase):
    def test_ranks_by_relevance(self):
        index = Bm25Index(records())
        self.assertEqual(index.search("collatz conjecture")[0], "record-0001")
        self.assertEqual(index.search("riemann zeros")[0], "record-0002")

    def test_no_match_returns_empty(self):
        self.assertEqual(Bm25Index(records()).search("sendov"), [])
        self.assertEqual(Bm25Index(records()).search(""), [])

    def test_deterministic_and_respects_k(self):
        index = Bm25Index(records())
        self.assertEqual(index.search("the", k=2), index.search("the", k=2))
        self.assertLessEqual(len(index.search("the", k=2)), 2)

    def test_tie_breaks_by_index_position(self):
        same = [
            {"record_id": "record-0001", "title": "x", "body": "alpha"},
            {"record_id": "record-0002", "title": "x", "body": "alpha"},
        ]
        self.assertEqual(Bm25Index(same).search("alpha"), ["record-0001", "record-0002"])
        self.assertEqual(Bm25Index(list(reversed(same))).search("alpha"), ["record-0002", "record-0001"])


if __name__ == "__main__":
    unittest.main()
