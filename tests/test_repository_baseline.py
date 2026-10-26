"""Checks for the public repository baseline, not the Crowsnest implementation."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepositoryBaselineTests(unittest.TestCase):
    def test_required_public_documents_exist(self):
        for name in ("README.md", "LICENSE", "CONTRIBUTING.md", "NEW-WORK.md"):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())
                self.assertTrue((ROOT / name).read_text().strip())

    def test_license_is_mit(self):
        license_text = (ROOT / "LICENSE").read_text()
        self.assertTrue(license_text.startswith("MIT License\n"))
        self.assertIn("Permission is hereby granted, free of charge", license_text)

    def test_document_relative_links_resolve(self):
        for document in ROOT.glob("*.md"):
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text()):
                if "://" not in target and not target.startswith("#"):
                    with self.subTest(document=document.name, target=target):
                        self.assertTrue((document.parent / target.split("#", 1)[0]).exists())

    def test_secret_and_runtime_patterns_are_ignored(self):
        patterns = set((ROOT / ".gitignore").read_text().splitlines())
        self.assertTrue({".env", ".env.*", "*.key", "identity.json", "state/", "artifacts/", ".venv/"} <= patterns)


if __name__ == "__main__":
    unittest.main()
