import os
import unittest


@unittest.skipUnless(os.environ.get("PARABOX_IMAGE_TESTS") == "1", "set PARABOX_IMAGE_TESTS=1 to run inside the code image")
class CodeImageTest(unittest.TestCase):
    def test_oracles_pass_the_verifier_and_the_audit(self):
        from parabox.tasks.code.selftest import selftest
        result = selftest()
        self.assertTrue(result["ok"], result["problems"])


if __name__ == "__main__":
    unittest.main()
