"""Exercise the ARM GRUB/initramfs repair without a guest or network."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


class ArchARMBootTests(unittest.TestCase):
    def test_config_uses_the_real_initramfs_and_guest_root_uuid(self):
        definition = yaml.safe_load((ROOT / 'images_yaml/archlinux.yaml').read_text())
        hook = next(a for a in definition['actions'] if 'hosted-arch-arm-initramfs' in a['action'])
        self.assertEqual(hook['types'], ['vm'])
        self.assertEqual(hook['architectures'], ['aarch64'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boot = root / 'boot'
            (boot / 'grub').mkdir(parents=True)
            initramfs = boot / 'initramfs-linux.img'
            initramfs.write_bytes(b'fixture-initramfs')
            defaults = root / 'default-grub'
            defaults.write_text('GRUB_EARLY_INITRD_LINUX_CUSTOM="vendor-microcode.img"\n')
            binary = root / 'bin'
            binary.mkdir()
            generator = binary / 'grub-mkconfig'
            generator.write_text('#!/bin/sh\nset -eu\n. "$GRUB_DEFAULT_FIXTURE"\n'
                                 'test "$GRUB_EARLY_INITRD_LINUX_CUSTOM" = "vendor-microcode.img initramfs-linux.img"\n'
                                 'printf "linux /boot/Image root=/dev/loop0p2 ro\\n  initrd /boot/vendor-microcode.img /boot/initramfs-linux.img\\n" > "$2"\n')
            generator.chmod(0o755)
            command = hook['action'].replace('/etc/default/grub', str(defaults)).replace('/boot', str(boot))
            environment = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'],
                               GRUB_DEFAULT_FIXTURE=str(defaults), DISTROBUILDER_ROOT_UUID='UUID=guest-fixture',
                               LXD_IMAGEBUILDER_ROOT_UUID='UUID=guest-fixture')
            for _ in range(2):
                subprocess.run(['sh', '-c', command], env=environment, check=True, timeout=5)
            self.assertEqual(defaults.read_text().count('# hosted-arm-initramfs-selection'), 1)
            config = (boot / 'grub/grub.cfg').read_text()
            self.assertIn('root=UUID=guest-fixture', config)
            self.assertIn('initrd /boot/vendor-microcode.img /boot/initramfs-linux.img', config)
            self.assertNotIn('/dev/loop', config)
            previous = defaults.read_bytes()
            initramfs.unlink()
            missing = subprocess.run(['sh', '-c', command], env=environment, capture_output=True, timeout=5)
            self.assertNotEqual(missing.returncode, 0)
            self.assertEqual(defaults.read_bytes(), previous)


if __name__ == '__main__':
    unittest.main()

