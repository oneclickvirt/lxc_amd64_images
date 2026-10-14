"""Source failures must not overwrite validated definitions or release indexes."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import append_image_actions as hooks
import refresh_image_sources as refresh
from verify_image_definitions import verify


DEFINITION = "image:\n  distribution: fixture\nsource:\n  downloader: fixture\nactions: []\nmappings:\n  architecture_map: {}\n"


class ImageSourceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        definitions = self.root / "images_yaml"
        definitions.mkdir()
        for distro in refresh.DISTROS:
            (definitions / (distro + ".yaml")).write_text(DEFINITION)
        (self.root / "all_images.txt").write_text("previous-valid-index\n")

    def tearDown(self):
        self.directory.cleanup()

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_hooks_follow_actions_even_when_mappings_is_last(self):
        path = self.root / "images_yaml/openwrt.yaml"
        hook = self.root / "hook.text"
        hook.write_text('- trigger: post-packages\n  action: |\n    #!/bin/sh\n    echo fixture\n')
        hooks.append(path, hook)
        hooks.append(path, hook)
        document = verify(path.read_text())
        self.assertEqual(len(document["actions"]), 1)
        self.assertEqual(document["mappings"], {"architecture_map": {}})

    def test_oracle_normalization_retains_gpg_and_all_variants(self):
        path = self.root / "images_yaml/oracle.yaml"
        path.write_text(DEFINITION + 'packages:\n  repositories:\n  - name: AppStream\n    variants: [cloud]\n    url: |\n      baseurl=http://yum.oracle.com/repo/OracleLinux/OL{{ image.release }}/appstream/$basearch/\n      enabled=1\n      gpgcheck=1\n')
        hooks.normalize_oracle(path)
        document = verify(path.read_text())
        repository = document["packages"]["repositories"][0]
        self.assertNotIn("variants", repository)
        self.assertIn("https://yum.oracle.com/", repository["url"])
        self.assertIn("gpgcheck=1", repository["url"])
        self.assertEqual(document["source"]["url"], "https://yum.oracle.com/ISOS/OracleLinux")
        original = path.read_bytes()
        path.write_bytes(original.replace(b"gpgcheck=1", b"gpgcheck=0"))
        rejected = path.read_bytes()
        with self.assertRaises(ValueError):
            hooks.normalize_oracle(path)
        self.assertEqual(path.read_bytes(), rejected)

    def test_el10_network_normalization_is_stable_and_preserves_el8_el9(self):
        path = self.root / 'images_yaml/almalinux.yaml'
        path.write_text(DEFINITION.replace('actions: []', 'actions:\n- trigger: post-files\n  types: [container]\n  releases: [9]\n  action: printf "dhcp=dhclient"') + 'packages:\n  sets:\n  - action: install\n    packages: [curl, dhclient]\n  - action: install\n    packages: [NetworkManager]\n    types: [container]\n    releases: [9]\n')
        hooks.normalize_el10(path)
        document = verify(path.read_text())
        for entry in document['packages']['sets']:
            if 'dhclient' in entry['packages']:
                self.assertEqual(set(map(str, entry['releases'])), {'8', '9'})
            if 'NetworkManager' in entry['packages']:
                self.assertIn('10', list(map(str, entry['releases'])))
        self.assertTrue(any('dhcp=internal' in e['action'] and e['releases'] == ['10'] for e in document['actions']))
        normalized = path.read_bytes()
        hooks.normalize_el10(path)
        self.assertEqual(path.read_bytes(), normalized)

    def test_failed_partial_source_refresh_preserves_every_original(self):
        before = self.snapshot()

        def failure(root, stage, repo, deadline):
            (stage / "oracle.yaml").write_text("incomplete download")
            raise RuntimeError("fixture transport failure")

        result = refresh.refresh(self.root, "lxc_amd64_images", prepare_stage=failure)
        self.assertEqual(result["status"], "deferred")
        self.assertTrue(result["used_validated_fallback"])
        self.assertEqual(self.snapshot(), before)

    def test_invalid_baseline_cannot_be_reported_as_fallback_success(self):
        (self.root / "images_yaml/openwrt.yaml").write_text("actions: [broken\n")
        with self.assertRaises(Exception):
            refresh.refresh(self.root, "lxc_amd64_images", prepare_stage=lambda *args: [])

    def test_generator_timeout_uses_validated_fallback_without_file_changes(self):
        scripts = self.root / ".github/scripts"
        scripts.mkdir(parents=True)
        for name in ["append_image_actions.py", "verify_image_definitions.py", "ci_network.sh"]:
            shutil.copy2(SCRIPTS / name, scripts / name)
        (scripts / "refresh_image_definitions.sh").write_text("#!/bin/bash\nsleep 30\n")
        for name in ["bash_insert_content.text", "sh_insert_content.text"]:
            (self.root / name).write_text("[]\n")
        before = self.snapshot()

        def short_budget(root, stage, repo, deadline):
            return refresh.prepare(root, stage, repo, time.monotonic() + 0.1)

        start = time.monotonic()
        with mock.patch.object(refresh, "api_json", return_value={"sha": "a" * 40}):
            result = refresh.refresh(self.root, "lxc_amd64_images", prepare_stage=short_budget)
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(result["status"], "deferred")
        self.assertEqual(self.snapshot(), before)

    def test_promotion_failure_rolls_back_previously_installed_files(self):
        before = self.snapshot()
        stage = self.root / "stage"
        stage.mkdir()
        (stage / "all_images.txt").write_text("new-valid-index\n")
        names = ["all_images.txt", "missing.txt"]
        with self.assertRaises(OSError):
            refresh.promote(self.root, stage, names)
        stage.rmdir()
        self.assertEqual(self.snapshot(), before)

    def test_release_indexes_use_uploaded_assets_and_ignore_staging_names(self):
        assets = [
            {"name": "debian_13_trixie_x86_64_cloud.zip", "state": "uploaded", "size": 100},
            {"name": "debian_13_trixie_arm64_cloud.zip", "state": "uploaded", "size": 100},
            {"name": "debian_13_trixie_arm64_default.zip", "state": "new", "size": 100},
            {"name": ".pending-1-debian_13_trixie_arm64_cloud.zip", "state": "uploaded", "size": 100},
            {"name": "oracle_9_9_arm64_cloud.zip", "state": "uploaded", "size": 100},
        ]
        releases = [{"draft": False, "prerelease": False, "tag_name": "debian", "assets": assets, "id": 1}]
        with mock.patch.object(refresh, "api_json", return_value=releases):
            indexes = refresh.release_indexes("incus_images", time.monotonic() + 10)
        self.assertEqual(indexes["x86_64_all_images.txt"], "debian_13_trixie_x86_64_cloud.zip\n")
        self.assertEqual(indexes["arm64_all_images.txt"], "debian_13_trixie_arm64_cloud.zip\n")

    def test_empty_release_catalog_does_not_replace_previous_index(self):
        before = self.snapshot()
        with mock.patch.object(refresh, "api_json", return_value=[]), self.assertRaises(ValueError):
            refresh.release_indexes("lxc_amd64_images", time.monotonic() + 10)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
