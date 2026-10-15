"""Run EL boot-layout repair against an EFI + root filesystem fixture."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from image_source_compat import rpm_vm_compat
from image_source_compat import normalize
from append_image_actions import serialize
from verify_image_definitions import verify
from refresh_image_sources import DISTROS


class RPMBootTests(unittest.TestCase):
    def test_bootstrap_dependencies_survive_a_fresh_upstream_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definitions = root / 'images_yaml'
            definitions.mkdir()
            for distro in DISTROS:
                document = {'image': {'distribution': distro}, 'source': {'downloader': 'fixture'}, 'actions': []}
                if distro == 'fedora':
                    document['actions'].append({'trigger': 'post-unpack', 'types': ['vm'], 'action': 'systemd-machine-id-setup'})
                if distro == 'gentoo':
                    document['packages'] = {'sets': [{'packages': ['app-admin/syslog-ng', 'sys-boot/grub'], 'action': 'install', 'types': ['vm'], 'variants': ['openrc']}]}
                    document['actions'].extend([
                        {'trigger': 'post-files', 'types': ['vm'], 'variants': ['openrc'], 'action': action}
                        for action in ('emerge gentoo-kernel-bin', 'grub-install --target=arm64-efi')])
                if distro == 'openeuler':
                    document['packages'] = {'sets': [{'packages': ['grub2-efi-aarch64'], 'action': 'install', 'types': ['vm'], 'architectures': ['aarch64']}]}
                (definitions / (distro + '.yaml')).write_text(serialize(document))
            normalize(root)
            snapshot = {p.name: p.read_bytes() for p in definitions.iterdir()}
            normalize(root)
            self.assertEqual(snapshot, {p.name: p.read_bytes() for p in definitions.iterdir()})
            fedora = verify((definitions / 'fedora.yaml').read_text())
            self.assertTrue(any(a['trigger'] == 'post-packages' and a['action'] == 'systemd-machine-id-setup' for a in fedora['actions']))
            gentoo = verify((definitions / 'gentoo.yaml').read_text())
            self.assertTrue(any('app-admin/syslog-ng' in s['packages'] and 'cloud' in s['variants'] for s in gentoo['packages']['sets']))
            for action in ('emerge gentoo-kernel-bin', 'grub-install --target=arm64-efi'):
                self.assertTrue(any(a['action'] == action and 'cloud' in a['variants'] for a in gentoo['actions']))
            efi = next(a for a in gentoo['actions'] if 'hosted-gentoo-efi-platform' in a['action'])
            self.assertEqual(efi['types'], ['vm'])
            self.assertEqual(efi['variants'], ['openrc', 'cloud'])
            self.assertIn('grub_platforms_efi-64', efi['action'])
            euler = verify((definitions / 'openeuler.yaml').read_text())
            self.assertTrue(any('grub2-efi-aa64' in s['packages'] for s in euler['packages']['sets']))
            debian = verify((definitions / 'debian.yaml').read_text())
            hook = next(a['action'] for a in debian['actions'] if 'hosted-debian-ssh-hostkeys' in a['action'])
            self.assertIn('ExecStartPre=\\nExecStartPre=/usr/bin/ssh-keygen -A', hook)
            self.assertIn('ExecStartPre=/usr/sbin/sshd -t', hook)

    def test_missing_ssh_keys_are_generated_at_boot_without_replacing_existing_keys(self):
        import configparser
        document = {'actions': []}
        rpm_vm_compat(document, 'centos')
        hook = next(a for a in document['actions'] if 'hosted-rpm-ssh-hostkeys' in a['action'])
        self.assertEqual(hook['types'], ['vm'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = hook['action'].replace('/etc/systemd/system', str(root / 'etc/systemd/system'))
            subprocess.run(['sh', '-c', command], check=True, timeout=5)
            self.assertFalse((root / 'etc/ssh').exists())
            service = configparser.ConfigParser(interpolation=None)
            service.read(root / 'etc/systemd/system/hosted-ssh-hostkeys.service')
            dropin = configparser.ConfigParser(interpolation=None)
            dropin.read(root / 'etc/systemd/system/sshd.service.d/10-host-keys.conf')
            self.assertEqual(dropin['Unit']['Requires'], 'hosted-ssh-hostkeys.service')
            self.assertEqual(dropin['Unit']['After'], 'hosted-ssh-hostkeys.service')
            self.assertEqual(service['Unit']['Before'], 'sshd.service')
            (root / 'etc/ssh').mkdir()
            args = service['Service']['ExecStart'].split() + ['-f', str(root)]
            subprocess.run(args, check=True, capture_output=True, timeout=15)
            keys = {p.name: p.read_bytes() for p in (root / 'etc/ssh').glob('ssh_host_*_key')}
            self.assertIn('ssh_host_ed25519_key', keys)
            subprocess.run(args, check=True, capture_output=True, timeout=15)
            self.assertEqual(keys, {p.name: p.read_bytes() for p in (root / 'etc/ssh').glob('ssh_host_*_key')})

    def test_raw_cloud_generator_disable_flag_is_removed_and_services_restored(self):
        import re
        from image_source_compat import raw_cloud_compat
        document = {'actions': []}
        raw_cloud_compat(document)
        raw_cloud_compat(document)
        self.assertEqual(len(document['actions']), 1)
        hook = document['actions'][0]
        self.assertEqual(hook['variants'], ['cloud'])
        self.assertEqual(hook['types'], ['container'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            disabled = root / 'etc/cloud/cloud-init.disabled'
            disabled.parent.mkdir(parents=True)
            disabled.touch()
            units = root / 'usr/lib/systemd/system'
            units.mkdir(parents=True)
            for name in ['cloud-init-local', 'cloud-init-main']:
                (units / (name + '.service')).touch()
            binary = root / 'bin'
            binary.mkdir()
            systemctl = binary / 'systemctl'
            systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n')
            systemctl.chmod(0o755)
            command = re.sub(r'/usr/lib/systemd/system|/lib/systemd/system|/etc/cloud|/etc/init.d',
                             lambda match: str(root / match.group().lstrip('/')), hook['action'])
            subprocess.run(['sh', '-c', command], check=True, timeout=5,
                           env=dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'], CALLS=str(root / 'calls')))
            self.assertFalse(disabled.exists())
            self.assertEqual((root / 'calls').read_text().splitlines(),
                             ['enable cloud-init-local.service', 'enable cloud-init-main.service'])

    def test_efi_forwarding_and_bls_paths_match_the_root_partition(self):
        for distro, vendor in [('almalinux', 'almalinux'), ('centos', 'centos'), ('rockylinux', 'rocky'), ('fedora', 'fedora')]:
            with self.subTest(distro=distro), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                boot = root / 'boot'
                (boot / 'grub2').mkdir(parents=True)
                (boot / 'loader/entries').mkdir(parents=True)
                (boot / 'grub2/grub.cfg').write_text('insmod blscfg\nblscfg\n')
                (boot / 'vmlinuz-1').write_text('kernel')
                (boot / 'initramfs-1.img').write_text('initramfs')
                entry = boot / 'loader/entries/test.conf'
                entry.write_text('linux /var/cache/distrobuilder.fixture/rootfs/boot/vmlinuz-1\ninitrd /var/cache/lxd-imagebuilder.fixture/rootfs/boot/initramfs-1.img\noptions $kernelopts\n')
                binary = root / 'bin'
                binary.mkdir()
                editenv = binary / 'grub2-editenv'
                editenv.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$ENV_LOG"\nif [ "$2" = create ]; then printf env > "$1"; fi\n')
                editenv.chmod(0o755)
                document = {'actions': []}
                rpm_vm_compat(document, distro)
                original = repr(document)
                rpm_vm_compat(document, distro)
                self.assertEqual(repr(document), original)
                hook = next(a for a in document['actions'] if 'hosted-rpm-efi-forwarder' in a['action'])
                command = hook['action'].replace('/boot', str(boot))
                environment = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'],
                                   DISTROBUILDER_ROOT_UUID='UUID=fixture-root', ENV_LOG=str(root / 'env.log'))
                for _ in range(2):
                    subprocess.run(['sh', '-c', command], env=environment, check=True, timeout=5)
                self.assertIn('linux ' + str(boot / 'vmlinuz-1'), entry.read_text())
                self.assertIn('initrd ' + str(boot / 'initramfs-1.img'), entry.read_text())
                self.assertNotIn('/var/cache/', entry.read_text())
                for directory in [vendor, 'BOOT']:
                    config = (boot / 'efi/EFI' / directory / 'grub.cfg').read_text()
                    self.assertIn('search --no-floppy --fs-uuid --set=dev fixture-root', config)
                    self.assertIn('configfile $prefix/grub.cfg', config)
                    self.assertIn('set prefix=($dev)', config)
                self.assertIn('blsdir=' + str(boot / 'loader/entries'), (root / 'env.log').read_text())
                (boot / 'vmlinuz-1').unlink()
                result = subprocess.run(['sh', '-c', command], env=environment, capture_output=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'Missing BLS boot image', result.stderr)


if __name__ == '__main__':
    unittest.main()
