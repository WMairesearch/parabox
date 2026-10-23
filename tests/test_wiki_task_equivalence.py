"""Pinned research-surface byte hashes; no research checkout needed to run tests."""

import ast
import json
from pathlib import Path
import unittest

from parabox.tasks.wiki import episode, evaluator, fixture
from parabox.tasks.wiki.runtime import budget, prompts, service
from parabox.util import digest_json, sha256


GOLDEN = {
    "fixtures": {
        "events": {
            "30": "2d097c5bb7cd3f6a04f041a263f8182f1a2d9f86d24d49d72d818517705bcc06",
            "60": "c394572ca00dc09a465758c9f72be98cd425d3350de59f97016ad57fcee0c156",
            "90": "2940416f02b5e8c8d7f780f0fe30279601f5e4e73f869a80dd614765e85d4859",
            "cases": "07348361f237a00b5ad0f419cc17c8afab9ab1eb33d6f206bc7963bec48382fa",
            "public": "03805b345fa50b1237882283cfa111e1ad37c3ad21c84bc34cf9f0bbb244e897",
            "problem": "c0fdb4f058e8285b4a0c6f3e42fba5c02b4d45bd666a0e2286cb06d0b6f403cb",
            "reference": "cfab178ec169c9f5e571d4c63fcb04c90c88d8cd9462833c9b434c4caea9c973"
        },
        "inventory": {
            "30": "892a1b0bdfe54f8af2d0ea530523448a2ee8d7395aadaf1b867f3a3bc6c0c766",
            "60": "246af5e3f63670da898cdebb71602db4b8e7daeef1863f4e6bc6bbbf32124893",
            "90": "c7cac3e51f0480ac445c2057c81991d2ae0dc5d3536e9877ae596fdcc743caf3",
            "cases": "16ef76e95264b89e6d99e71f790e0a9c07476eddecd081cd0c93a202eaf567c8",
            "public": "fac356923ecdb1d8d40e8200a5099aa19b55fa84399a9eb05364ec817f61abc1",
            "problem": "3f75bbe4c9f179fb2f5f565385a27c1fa7df9280e54557a7072af676454d4195",
            "reference": "efab9b9d8648629c8f25fad4956763ff0b08099b23052bc9cb8b9cb9c88b72bd"
        },
        "access_logs": {
            "30": "d5ad3f75aeffd802d96e48bb06fb1cbc6e9fce5b9610aa3d8424bb31f7c0e908",
            "60": "6189f4ceb6cfbaff0385094bf730c34e7a3677a3be9ed00f68f67ff92fc50beb",
            "90": "9b5ba890bef167b4b080d673aa2b19c879f9078045d9524e19c7800532c9ff53",
            "cases": "3a1b92c55ae1e75884bea879f3fbea33f881afc3711d1d7a1e39c58638945905",
            "public": "73cb80275166601c891c5299d01ca4dfc1f1c4650553adf72bc169c4e45e38d4",
            "problem": "65a9d54f5ee6ac0f8ddbe540c6f81d002fa7a733d20a9d087a47d23c879f88d6",
            "reference": "f3d386ad2f26d5a8ba4bfd05ac20b14a0cca837e48b0f3d9dd8e5dbb14b303b4"
        }
    },
    "surfaces": {
        "events:30:False:0:60": "3c775a359124144780faac337eb270506928c05fde187433e9b1d387edad6959",
        "events:30:False:0:20": "7a60a7499e0d7fa41b3697cb8581b6aa24064eb078b468e642ffa8c810b64163",
        "events:30:False:2:60": "d7dfc178de4dd8e9fea85e9006cd20d3fba402763d99ee245ed55ae33f792fe7",
        "events:30:False:2:20": "497eb38a680542edfb5c857cbf91dd3e151e6c55549192bd3b3bdd58d806e493",
        "events:60:False:0:60": "141ff55ddf5d557ffa4564454ea181797b676a2ef39c12bd3e19578f1ff62b9a",
        "events:60:False:0:20": "db1b58acfe2abab328955dee144579fd9befc90b40e9c2512e59efb353fe9325",
        "events:60:False:2:60": "dedcbd398812b4d1ba5f17f91373ec3231bca7589d0eb938d221512dad77a6ff",
        "events:60:False:2:20": "0cb8f6fd38fbc03856d5c5e191e29dc09abf593a87320856049d4f5641cce4de",
        "events:90:False:0:60": "549b11b89890ca452dd434a2e4fa1188a1a395bbab66dbf43d2fccbb95d21969",
        "events:90:False:0:20": "58bf68f376319edb837434ab8d8193e0fa7ea0440003634f0b32b4bbc22f3539",
        "events:90:False:2:60": "9bcf374309cb53111f4db1b026e88447f43274db2016e0c8e9719a91750e47df",
        "events:90:False:2:20": "78b8abdf72d6b2d4c0093be633d0b49656b579a7b84db4d6e72d57d05ec6a39c",
        "events:30:True:0:60": "014b48ba4c7d64ba9aa796214525da3e231a6562aad71c38489e3d316134d6a0",
        "events:30:True:2:60": "68004d4e8fb4708ca83d9574584f609b940dd4bd1e3a146f3413b0448f1aab9c",
        "events:60:True:0:60": "7a27409e1843e826806f4c4e02be824dfe07e4118b514615c219679ec3d1b0c5",
        "events:60:True:2:60": "de6c3a511435a1062219479882c376cc77b6fe06b2477e8f45932fe6cb6b44c0",
        "events:90:True:0:60": "3e0e1c4fa509563b5441c6293654712c66f2e2076a6d6b608f03d579ce5f1ca0",
        "events:90:True:2:60": "4979dd939d88345b6a6fb633a6e72b62e623de1d5652bb18db3c5a0128166edd",
        "inventory:30:False:0:60": "2cb257c594196cdead5882470a91fea5442d488ba5b455b0835107a1c71f7444",
        "inventory:30:False:0:20": "8a48a9d0cd701c2b5ccd999022331f2f4557457a038219409a7445649bd3e76f",
        "inventory:30:False:2:60": "969608337e19f0c95845fa9defd76063163bff84e9c11c792a5274cb9e3e4e69",
        "inventory:30:False:2:20": "ff878d675d1a2d934ece2e9a20a0f38aa9a816e5e6bac00da38213abb99a7438",
        "inventory:60:False:0:60": "7f0979cbe83dc3f532e532432e8030586470311fdefe307c47a0143f6d9e7a55",
        "inventory:60:False:0:20": "08ae224b28b9910dfd7341eeae9cd31f3af2b90fd8aef73038ca1a1a7703f8a5",
        "inventory:60:False:2:60": "abe76d33a1b24fc809d079f2f4cebb885e31eea02dc73811fa9c30eb258f7a4f",
        "inventory:60:False:2:20": "3937ddc79c5c85f769a418c65f3c4a66c16c41b616197650653c795b20137fa6",
        "inventory:90:False:0:60": "d54b9693fb6a535bbd27a3e8901484b5cd7ae1c4486e64ca312fe2775376a50b",
        "inventory:90:False:0:20": "32727a3ad4d9ed526fe8eee38f82d9205239205bcd986306b21ccf0e5e604662",
        "inventory:90:False:2:60": "64f0f26c8b2c5116af71283a458370a0cabca5c7cc163b6847682fbf78f2cc31",
        "inventory:90:False:2:20": "a7f12341d05dd131e6c16d9f778bd66a609fd173933dd3709b7a3d3ef0c46bd1",
        "inventory:30:True:0:60": "78f3de4eea0621f5aeecd18b817f33fbbbb05325b1eb1d7f2a94d0e96c9638b1",
        "inventory:30:True:2:60": "2c50e7b50efed2d209c5b8911c355d967a000f064d21a4ffd7733782660a04f7",
        "inventory:60:True:0:60": "361a200578985dc0a535352a9b06c099090f1fff013801b7923f212bc6f38cd8",
        "inventory:60:True:2:60": "c21e853d4aca2c7f10ec150f554986eadac6b75acd8c1782584b2f462b6ace40",
        "inventory:90:True:0:60": "c986d33f3e65f66cac22199a1c3ff96e12a99a03d97f056d18b3ba68adfc1d74",
        "inventory:90:True:2:60": "c411c55d142cfdf39d9d0479759d0ee722591ee2b4cfd353b57c5580b9588ecc",
        "access_logs:30:False:0:60": "21f4abac2306dee8c54aea1a4c8ef675d7aae83bbeb132ec70a62771cf71f96b",
        "access_logs:30:False:0:20": "1c4a2b8400924f3798edf0e7a98e5a645d56791f6d32af7559e140f2dc43245e",
        "access_logs:30:False:2:60": "b5f1d48dd8164fd04661ddf942a7b44d81d7c4efbcf054838240abb3608ba13d",
        "access_logs:30:False:2:20": "4a919a8ae8022af0cecdb205f0118c58c87257a8934b1a8ebf46e8a7f85e668d",
        "access_logs:60:False:0:60": "13c0f16f52ea36f9e80b6d55439f513e1d9acc312ad97246ea922819ab9332c0",
        "access_logs:60:False:0:20": "2711de6b14349ee268dac3a4c08d97b8ee56e3dacad76b3fbd3b197a7a6cff36",
        "access_logs:60:False:2:60": "f43b712911dd3fea1ccb6523c1b03c168b133a50963cc9811d04f09d8316d28f",
        "access_logs:60:False:2:20": "3b21aeafff388e8961c65e900873f8361481920047f77545189ee7b1aff2d7cc",
        "access_logs:90:False:0:60": "8b35901f3b06225795afdbc012d5ee1e0688f153cb675da0f81418a735b14e33",
        "access_logs:90:False:0:20": "ffc65bb716fb226490764f21e81dbd7095ddb5c85f37bb8e2cb8f804537e5bd8",
        "access_logs:90:False:2:60": "f3d85aea7dcc08922909f0479d967ebc75eb7baba76492c7d126e4b7f6dee7a4",
        "access_logs:90:False:2:20": "4895193f07b8370023a30e59128167a5ac339467829b24f36d4f0b46439a5458",
        "access_logs:30:True:0:60": "3771ee71057cf335529d4542096921d15c150662e755f3d330b79f65a4bd4a3e",
        "access_logs:30:True:2:60": "716212ba61753ae28dac267a5dca31084ce8ba6493924162cc2babfc023fb0d1",
        "access_logs:60:True:0:60": "76da42d95e1f98e2ed4ef7544dc28eb8f5b353da446f4bf8d2fa83a901aa1c2d",
        "access_logs:60:True:2:60": "ce8c3de0bccc1990a41914a782ec2b356226dace14804bbf57b496796e695e30",
        "access_logs:90:True:0:60": "24ec1fcec7a70941b34b90d5bf07187d3fed18dfa1a2142ff9575c600133e268",
        "access_logs:90:True:2:60": "92a1d017335ef172e04fa83e6c8d54d684719d99c83564a47197ee8a665ddadd"
    },
    "assignments": {
        "events:False": "6265edf73c0c3b3559642b213cf730ac47f0175261dc201f4b8679e4e5296aa4",
        "events:True": "6ac3cc058916cb867838903cb8959be5a16d13c46059908137b6423b25f55263",
        "inventory:False": "5ef9c1d33e001f3e1d0c9e24ca1982ae3bbcb5b3e478e91096834639e0ab3c7d",
        "inventory:True": "6ac3cc058916cb867838903cb8959be5a16d13c46059908137b6423b25f55263",
        "access_logs:False": "672afb2490311b253510d1fc0f9231a639931290d6d07566ba421314ae2a55b8",
        "access_logs:True": "6ac3cc058916cb867838903cb8959be5a16d13c46059908137b6423b25f55263"
    },
    "tools": "bcfb4d2a49298aed9f9994bc4c68875b852c1f70e72a5e155bf5425a91cb9fcc",
    "system": "5777cf0e8b8cfdc32ba890cac55f5d441080b7dfb4577c7a431605241e573484",
    "service_client": "f660ac54850af3dcfad7ba4cf18a86d49aa2a1c2178babd7a25783cc50561b0d",
    "grading_runner": "40dae3e70dda6904528b51b96f5e89e3f757086a1f354150899fa921f5a7333b"
}


class SurfaceEquivalenceTests(unittest.TestCase):
    def test_all_fixtures_match_frozen_bytes(self):
        self.assertEqual(set(fixture.packages()), set(GOLDEN["fixtures"]))
        for package in fixture.packages():
            actual = {"cases": digest_json(fixture.cases(package)),
                      "public": digest_json(fixture.public_cases(package)),
                      "problem": sha256(fixture.problem(package)),
                      "reference": sha256(fixture.reference_source(package)),
                      **{str(score): sha256(fixture.starter_source(package, score))
                         for score in (30, 60, 90)}}
            self.assertEqual(actual, GOLDEN["fixtures"][package], package)
            self.assertEqual(len(fixture.cases(package)), 100)
            self.assertEqual(len(fixture.public_cases(package)), 4)

    def test_all_rendered_files_match_frozen_bytes(self):
        for key, expected in GOLDEN["surfaces"].items():
            package, score, source, count, limit = key.split(":")
            successors = [] if count == "0" else ["events", "inventory"]
            if limit == "20":
                files = budget.workspace_files(package, int(score), successors)
            else:
                files = prompts.workspace_files(package, int(score), source=source == "True",
                                                successors=successors)
            self.assertEqual(digest_json({name: sha256(raw) for name, raw in files.items()}),
                             expected, key)

    def test_messages_tools_and_executed_helpers_match(self):
        self.assertEqual(digest_json(episode.TOOLS), GOLDEN["tools"])
        self.assertEqual(sha256(episode.SYSTEM), GOLDEN["system"])
        self.assertEqual(sha256(service.CLIENT), GOLDEN["service_client"])
        self.assertEqual(sha256(evaluator.RUNNER), GOLDEN["grading_runner"])
        for key, expected in GOLDEN["assignments"].items():
            package, source = key.split(":")
            self.assertEqual(sha256(prompts.assignment(package, source == "True")), expected)

    def test_package_has_no_research_imports_or_paths(self):
        for path in Path(episode.__file__).parent.glob("*.py"):
            text = path.read_text()
            self.assertNotIn("/home/ast/", text, path.name)
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith("scripts"), path.name)
                elif isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name.startswith("scripts") for alias in node.names),
                                     path.name)

    def test_case_objects_are_detached(self):
        original = fixture.cases("events")
        changed = fixture.cases("events")
        changed[0]["input"].clear()
        changed[0]["expected"].clear()
        self.assertEqual(fixture.cases("events"), original)


if __name__ == "__main__":
    unittest.main()
