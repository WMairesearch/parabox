import unittest
from pathlib import Path

from parabox.studies.transmission import notes
from parabox.util import ROOT, sha256


class PackagedSeedTest(unittest.TestCase):
    def test_packaged_seed_matches_frozen_source(self):
        packaged = Path(notes.__file__).parent / "assets" / "transmission-correction.txt"
        original = ROOT / "data" / "seeds" / packaged.name
        self.assertEqual(packaged.read_bytes(), original.read_bytes())
        self.assertEqual(sha256(packaged.read_bytes()), notes.CONDEMN_SHA256)


if __name__ == "__main__":
    unittest.main()
