import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


def public_prose():
    sources = list(ROOT.glob("*.md"))
    for directory in ("docs", "report", "configs", "data", ".github"):
        sources.extend((ROOT / directory).rglob("*.md"))
    sources.extend((ROOT / "report" / "decks").rglob("*.tex"))
    return sources


class PublicDocsTest(unittest.TestCase):
    def test_public_prose_uses_descriptive_study_names(self):
        for source in public_prose():
            with self.subTest(source=source.relative_to(ROOT)):
                content = source.read_text()
                self.assertNotRegex(content, r"\b[Ff]\d+(?:\.\d+)*\b")
                self.assertNotRegex(content, r"\b(?:Round|round|Backup) [A-Z]\b")
                self.assertNotRegex(content, r"\b[Tt]able [A-Z]\b")
                self.assertNotRegex(content, r"\b[Aa]rms?\b")
                self.assertNotRegex(content, r"[\u4e00-\u9fff]")
                self.assertNotIn("/home/ast/", content)

    def test_public_prose_has_no_stale_editorial_instructions(self):
        for source in public_prose():
            with self.subTest(source=source.relative_to(ROOT)):
                content = source.read_text()
                self.assertNotRegex(content, r"(?i)falsifier\s+falsifier")
                self.assertNotIn("What changes in the short deck", content)
                self.assertNotIn("redo.md", content)
                self.assertNotIn("Parent review", content)
                self.assertNotIn("extended budget agents", content)
                self.assertNotIn("replication generations", content)
                self.assertNotRegex(content, r"(?:extended budget|replication) = [48]")

    def test_deck_uses_default_theme_and_combines_the_incident_accounts(self):
        deck = (ROOT / "report/decks/spread-of-misalignment/short.tex").read_text()
        self.assertIn(r"\usetheme{default}", deck)
        self.assertIn(r"\usecolortheme{default}", deck)
        self.assertNotIn(r"\setbeamercolor", deck)
        self.assertNotIn(r"\definecolor", deck)
        self.assertNotIn(r"\setbeamerfont{frametitle}", deck)
        self.assertNotIn(r"\insertframenumber", deck)
        self.assertNotIn("[frame number]", deck)
        frames = deck.split(r"\begin{frame}")
        self.assertIn("Hugging Face intrusion", frames[2])
        self.assertIn("Theorem-proving collective", frames[2])
        self.assertIn("risked failing", frames[2])
        self.assertIn("Shared records connect incidents across settings", frames[3])
        self.assertIn("DseWiki", frames[3])
        self.assertIn("UK AISI testing", frames[3])
        self.assertIn("publication dates", frames[3])

    def test_task_audits_and_framework_security_have_distinct_documentation(self):
        readme = (ROOT / "README.md").read_text()
        security = (ROOT / "SECURITY.md").read_text().lower()
        self.assertIn("independent execution audit", readme)
        self.assertIn("[Security](SECURITY.md)", readme)
        self.assertIn("third-party security audit", security)

    def test_report_connects_resources_and_successor_behavior(self):
        report = (ROOT / "report/README.md").read_text()
        self.assertIn("(resource-allocation/README.md)", report)
        self.assertIn("(shared-test-wiki/README.md)", report)
        for source in public_prose():
            with self.subTest(source=source.relative_to(ROOT)):
                self.assertNotIn("stronger endpoint", source.read_text().lower())

    def test_research_scope_does_not_require_a_shared_group(self):
        paths = [ROOT / "README.md", ROOT / "pyproject.toml",
                 ROOT / "report/decks/spread-of-misalignment/short.tex",
                 ROOT / "report/decks/spread-of-misalignment/README.md"]
        for source in paths:
            with self.subTest(source=source.relative_to(ROOT)):
                self.assertNotRegex(source.read_text(), r"(?i)\bswarms?\b")
        deck = (ROOT / "report/decks/spread-of-misalignment/short.tex").read_text()
        self.assertIn(r"\title{The Spread of Misalignment}", deck)
        self.assertIn("across system and task boundaries", deck)

    def test_documentation_has_an_explicit_distribution_inventory(self):
        lines = (ROOT / "MANIFEST.in").read_text().splitlines()
        self.assertIn("prune docs", lines)
        self.assertIn("prune report", lines)
        self.assertFalse(any(line.startswith("recursive-include docs") for line in lines))
        self.assertFalse(any(line.startswith("recursive-include report") for line in lines))
        listed = {line.removeprefix("include ") for line in lines
                  if line.startswith(("include docs/", "include report/"))
                  and Path(line).suffix in {".md", ".tex", ".bib", ".pdf", ".png", ".py"}}
        actual = {path.relative_to(ROOT).as_posix() for directory in ("docs", "report")
                  for path in (ROOT / directory).rglob("*")
                  if path.is_file() and path.suffix in {".md", ".tex", ".bib", ".pdf", ".png", ".py"}
                  and path.name not in {"short.pdf", "main.pdf"}}
        self.assertEqual(listed, actual)
        self.assertFalse(any("*" in name for name in listed))

    def test_report_evidence_has_an_explicit_distribution_inventory(self):
        lines = (ROOT / "MANIFEST.in").read_text().splitlines()
        listed = {line.removeprefix("include ") for line in lines
                  if line.startswith("include report/") and Path(line).suffix in {".csv", ".json"}}
        actual = {path.relative_to(ROOT).as_posix() for path in (ROOT / "report").rglob("*")
                  if path.is_file() and path.suffix in {".csv", ".json"}
                  and "continuation" not in path.parts and "review" not in path.parts}
        self.assertEqual(listed, actual)
        self.assertFalse(any("*" in name for name in listed))

    def test_active_references_use_the_public_layout(self):
        sources = list((ROOT / "scripts").glob("*.py"))
        sources += list((ROOT / ".github").rglob("*.yml"))
        sources += list((ROOT / "docs").rglob("*.md"))
        sources += list((ROOT / "report").rglob("*.md"))
        for source in sources:
            with self.subTest(source=source.relative_to(ROOT)):
                content = source.read_text()
                self.assertNotRegex(content, r"data/(?:final|composition|mechspan|population|longchain)/")
                self.assertNotRegex(content, r"docs/(?:decks|studies)/")
                self.assertNotIn("/home/ast/", content)

    def test_relative_markdown_links_resolve(self):
        files = [source for source in public_prose() if source.suffix == ".md"]
        for source in files:
            for target in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", source.read_text()):
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                with self.subTest(source=source.relative_to(ROOT), target=target):
                    self.assertTrue((source.parent / unquote(parsed.path)).exists())

    def test_data_contains_only_runtime_inputs(self):
        self.assertEqual({path.name for path in (ROOT / "data").iterdir()},
                         {"README.md", "corpus", "seeds"})
        for directory in ("final", "composition", "mechspan", "population", "longchain"):
            self.assertTrue((ROOT / "report" / directory).is_dir())

    def test_protocol_container_configuration_is_distributed(self):
        self.assertTrue((ROOT / ".containers" / "containers.conf").is_file())
        self.assertIn("include .containers/containers.conf",
                      (ROOT / "MANIFEST.in").read_text().splitlines())


if __name__ == "__main__":
    unittest.main()
