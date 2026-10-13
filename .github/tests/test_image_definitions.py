"""Regression cases for misplaced hooks and silently overwritten YAML keys."""
import importlib.util
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "image_definitions", ROOT / ".github/scripts/verify_image_definitions.py"
)
definitions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(definitions)
BASE = "image:\n  distribution: fixture\nsource:\n  downloader: fixture-http\n"


class ImageDefinitionTests(unittest.TestCase):
    def test_misplaced_hook_after_mappings_is_rejected(self):
        with self.assertRaises(yaml.YAMLError):
            definitions.verify(BASE + "mappings:\n  architecture_map: fixture\n- trigger: post-files\n  action: echo broken\n")

    def test_duplicate_actions_never_discard_existing_hooks(self):
        with self.assertRaises(yaml.YAMLError):
            definitions.verify(BASE + "actions: []\nactions: []\n")

    def test_oracle_default_variant_has_signed_appstream(self):
        document = definitions.verify((ROOT / "images_yaml/oracle.yaml").read_text())
        appstream = next(r for r in document["packages"]["repositories"] if r["name"] == "AppStream")
        self.assertIn("default", appstream.get("variants", ["default", "cloud"]))
        self.assertIn("baseurl=https://yum.oracle.com/", appstream["url"])
        self.assertIn("gpgcheck=1", appstream["url"])

    def test_valid_hook_and_mapping_are_preserved(self):
        parsed = definitions.verify(BASE + "actions:\n- trigger: post-files\n  action: echo valid\nmappings:\n  architecture_map: fixture\n")
        self.assertEqual(parsed["actions"][0]["action"], "echo valid")
        self.assertEqual(parsed["mappings"]["architecture_map"], "fixture")


if __name__ == "__main__":
    unittest.main()
