"""Test archive corruption, read-only selection and failed-builder contracts."""
import importlib.util
import io
import lzma
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("image_outputs", ROOT / ".github/scripts/verify_image_outputs.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class ImageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        self.previous = Path.cwd()
        os.chdir(self.folder)

    def tearDown(self):
        os.chdir(self.previous)
        self.directory.cleanup()

    def check(self, name):
        verifier.verify(name, minimum=0, maximum=1024 * 1024)

    def test_valid_zip_and_crc_corruption(self):
        with zipfile.ZipFile("image.zip", "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("rootfs", b"fixture-payload")
        self.check("image.zip")
        path = Path("image.zip")
        path.write_bytes(path.read_bytes().replace(b"fixture-payload", b"corrupt-payload"))
        with self.assertRaises(ValueError):
            self.check("image.zip")

    def test_tar_xz_checksum_including_trailing_bytes(self):
        with tarfile.open("image.tar.xz", "w:xz") as archive:
            metadata = tarfile.TarInfo("etc/os-release")
            metadata.size = 7
            archive.addfile(metadata, io.BytesIO(b"fixture"))
        self.check("image.tar.xz")
        path = Path("image.tar.xz")
        content = bytearray(path.read_bytes())
        content[-16] ^= 1
        path.write_bytes(content)
        with self.assertRaises((lzma.LZMAError, tarfile.ReadError, ValueError, EOFError)):
            self.check("image.tar.xz")

    def test_lightweight_openwrt_archive_requires_rootfs_identity(self):
        name = "openwrt_25.12_25.12_x86_64_default.tar.xz"
        payload = os.urandom(1024 * 1024 + 4096)
        for identified in [False, True]:
            with tarfile.open(name, "w:xz") as archive:
                binary = tarfile.TarInfo("bin/busybox")
                binary.size = len(payload)
                archive.addfile(binary, io.BytesIO(payload))
                if identified:
                    identity = tarfile.TarInfo("./etc/openwrt_release")
                    identity.size = 7
                    archive.addfile(identity, io.BytesIO(b"fixture"))
            self.assertLess(Path(name).stat().st_size, 10 * 1024 * 1024)
            if identified:
                verifier.verify(name)
            else:
                with self.assertRaisesRegex(ValueError, "identity"):
                    verifier.verify(name)
        Path("unidentified.tar.xz").write_bytes(Path(name).read_bytes())
        with self.assertRaisesRegex(ValueError, "size"):
            verifier.verify("unidentified.tar.xz")

    def test_missing_empty_and_unsafe_outputs_are_rejected(self):
        Path("empty.tar.xz").write_bytes(b"")
        for filename in ["missing.zip", "empty.tar.xz", "../image.zip", "LICENSE"]:
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                self.check(filename)

    def run_builder(self, script, release, build=False, catalog_unavailable=False, distro="debian", catalog_releases="bookworm trixie", variants=""):
        # No provisioning or network in the fixture. All dependency commands are present.
        bin_dir = self.folder / "bin"
        bin_dir.mkdir(exist_ok=True)
        for name in ["apt-get", "zip", "jq", "snap", "umoci", "debootstrap", "systemctl", "sleep"]:
            path = bin_dir / name
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o755)
        catalog = bin_dir / "curl"
        catalog.write_text("""#!/bin/sh
if [ "$IMAGE_TEST_CATALOG_FAIL" = 1 ]; then exit 22; fi
printf 'name: release\n'
for item in $IMAGE_TEST_CATALOG; do printf '  - %s\n' "$item"; done
printf '\n'
""")
        catalog.chmod(0o755)
        sudo = bin_dir / "sudo"
        sudo.write_text('#!/bin/sh\nexec "$@"\n')
        sudo.chmod(0o755)
        for name in ["distrobuilder", "lxd-imagebuilder"]:
            path = bin_dir / name
            path.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$IMAGE_TEST_CALLS"\nexit 17\n')
            path.chmod(0o755)
        environment = dict(os.environ, CI_IMAGE_VARIANTS=variants, IMAGE_TEST_CATALOG=catalog_releases, CI_IMAGE_RELEASES=release, IMAGE_TEST_CATALOG_FAIL="1" if catalog_unavailable else "0", IMAGE_TEST_CALLS=str(self.folder / "calls"),
                           PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])
        bash = shutil.which("bash")
        # macOS's system Bash predates ${var,,}, used by these existing scripts.
        if Path("/opt/homebrew/bin/bash").exists():
            bash = "/opt/homebrew/bin/bash"
        return subprocess.run([bash, str(script), distro, "true" if build else "false", "amd64"],
                              env=environment, capture_output=True, text=True, timeout=15)

    def scripts(self):
        return [p for p in [ROOT / "build_images.sh", ROOT / "build_kvm_images.sh"] if p.exists()]

    def test_gentoo_variant_selection_is_exact_and_read_only(self):
        for variant in ["cloud", "openrc", "systemd"]:
            with self.subTest(variant=variant):
                result = self.run_builder(ROOT / "build_images.sh", "current", distro="gentoo", variants=variant)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(result.stdout.splitlines()[-1].split()), 1)
                self.assertIn("_" + variant + ".tar.xz", result.stdout)
                self.assertFalse(Path("calls").exists())
        result = self.run_builder(ROOT / "build_images.sh", "current", distro="gentoo", variants="unknown")
        self.assertNotEqual(result.returncode, 0)

    def test_openwrt_stable_and_snapshot_package_managers(self):
        for release, manager in [("24.10", "opkg"), ("25.12", "apk"), ("snapshot", "apk")]:
            with self.subTest(release=release):
                Path("calls").unlink(missing_ok=True)
                result = self.run_builder(ROOT / "build_images.sh", release, build=True, distro="openwrt")
                self.assertNotEqual(result.returncode, 0)
                call = Path("calls").read_text().splitlines()
                self.assertEqual(len(call), 1)
                self.assertIn("packages.manager=" + manager, call[0])
                self.assertIn("image.release=" + release, call[0])

    def test_oracle_10_uses_official_source_without_verification_bypass(self):
        result = self.run_builder(ROOT / "build_images.sh", "10", build=True,
                                  distro="oracle", catalog_releases="8 9 10")
        self.assertNotEqual(result.returncode, 0)
        call = Path("calls").read_text()
        self.assertIn("source.url=https://yum.oracle.com/ISOS/OracleLinux", call)
        self.assertNotIn("skip_verification=true", call)

    def test_release_10_never_disables_iso_verification(self):
        for distro in ["almalinux", "rockylinux"]:
            with self.subTest(distro=distro):
                Path("calls").unlink(missing_ok=True)
                result = self.run_builder(ROOT / "build_images.sh", "10", build=True,
                                          distro=distro, catalog_releases="8 9 10")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("skip_verification=true", Path("calls").read_text())

    def test_release_listing_is_exact_and_keeps_existing_images(self):
        for script in self.scripts():
            with self.subTest(script=script.name):
                Path("existing.tar.xz").write_bytes(b"previous-good-image")
                Path("disk.qcow2").write_bytes(b"previous-good-vm")
                result = self.run_builder(script, "trixie")
                self.assertEqual(result.returncode, 0, result.stderr)
                names = result.stdout.splitlines()[-1].split()
                self.assertEqual(len(names), 2)
                self.assertTrue(all("_13_trixie_" in name for name in names))
                self.assertEqual(Path("existing.tar.xz").read_bytes(), b"previous-good-image")
                self.assertEqual(Path("disk.qcow2").read_bytes(), b"previous-good-vm")
                self.assertFalse(Path("calls").exists())

    def test_upstream_http_failure_uses_frozen_supported_catalog(self):
        result = self.run_builder(ROOT / "build_images.sh", "trixie", catalog_unavailable=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all("_13_trixie_" in n for n in result.stdout.splitlines()[-1].split()))
        self.assertFalse(Path("calls").exists())

    def test_unknown_release_and_distribution_fail(self):
        for script in self.scripts():
            with self.subTest(script=script.name):
                result = self.run_builder(script, "missing-release")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("No images match", result.stderr)

    def test_builder_failure_stops_batch_with_exact_selected_release(self):
        for script in self.scripts():
            with self.subTest(script=script.name):
                Path("calls").unlink(missing_ok=True)
                result = self.run_builder(script, "trixie", build=True)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                calls = Path("calls").read_text().splitlines()
                self.assertEqual(len(calls), 1)
                self.assertIn("image.release=trixie", calls[0])
                self.assertFalse(list(self.folder.glob("*.zip")))


if __name__ == "__main__":
    unittest.main()
