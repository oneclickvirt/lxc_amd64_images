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

    def test_missing_empty_and_unsafe_outputs_are_rejected(self):
        Path("empty.tar.xz").write_bytes(b"")
        for filename in ["missing.zip", "empty.tar.xz", "../image.zip", "LICENSE"]:
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                self.check(filename)

    def run_builder(self, script, release, build=False):
        # No provisioning or network in the fixture. All dependency commands are present.
        bin_dir = self.folder / "bin"
        bin_dir.mkdir(exist_ok=True)
        for name in ["apt-get", "zip", "jq", "snap", "umoci", "debootstrap", "systemctl", "sleep"]:
            path = bin_dir / name
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o755)
        sudo = bin_dir / "sudo"
        sudo.write_text('#!/bin/sh\nexec "$@"\n')
        sudo.chmod(0o755)
        for name in ["distrobuilder", "lxd-imagebuilder"]:
            path = bin_dir / name
            path.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$IMAGE_TEST_CALLS"\nexit 17\n')
            path.chmod(0o755)
        environment = dict(os.environ, CI_IMAGE_RELEASES=release, IMAGE_TEST_CALLS=str(self.folder / "calls"),
                           PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])
        bash = shutil.which("bash")
        # macOS's system Bash predates ${var,,}, used by these existing scripts.
        if Path("/opt/homebrew/bin/bash").exists():
            bash = "/opt/homebrew/bin/bash"
        return subprocess.run([bash, str(script), "debian", "true" if build else "false", "amd64"],
                              env=environment, capture_output=True, text=True, timeout=15)

    def scripts(self):
        return [p for p in [ROOT / "build_images.sh", ROOT / "build_kvm_images.sh"] if p.exists()]

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
