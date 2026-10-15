"""Exercise release identity repair without weakening rootfs metadata."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from image_ssh_identity import KEY_PATH, runtime_files
from repair_image_hostkeys import inventory, repair_tar, repair_directory


class ImageIdentityTests(unittest.TestCase):
    def test_stream_repair_preserves_packages_owners_links_and_xattrs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original, target = root / 'original.tar.xz', root / 'safe.tar.xz'
            records = {
                'etc/ssh/ssh_host_ed25519_key': b'fixture identity must be removed',
                'etc/ssh/ssh_host_ed25519_key.pub': b'fixture public identity',
                'etc/ssh/authorized_keys': b'authorized user remains intact',
                'usr/lib/systemd/system/ssh.service': b'[Service]\nExecStartPre=/usr/sbin/sshd -t\n',
                'usr/bin/ssh-keygen': b'packaged command',
                'usr/bin/app': b'unmodified package payload',
            }
            with tarfile.open(original, 'w:xz') as archive:
                for name, data in records.items():
                    entry = tarfile.TarInfo('./' + name)
                    entry.uid, entry.gid, entry.mode = 123, 456, 0o751
                    entry.pax_headers = {'SCHILY.xattr.user.fixture': 'retained attribute'}
                    entry.size = len(data)
                    archive.addfile(entry, io.BytesIO(data))
                link = tarfile.TarInfo('./bin')
                link.type, link.linkname = tarfile.SYMTYPE, 'usr/bin'
                archive.addfile(link)
            self.assertEqual(repair_tar(original, target), 2)
            self.assertFalse(any(KEY_PATH.fullmatch(name) for name in inventory(target)))
            with tarfile.open(target, 'r:xz') as archive:
                by_name = {member.name.removeprefix('./'): member for member in archive}
                for name, data in records.items():
                    if KEY_PATH.fullmatch(name):
                        continue
                    entry = by_name[name]
                    self.assertEqual(archive.extractfile(entry).read(), data)
                    self.assertEqual((entry.uid, entry.gid, entry.mode), (123, 456, 0o751))
                    self.assertEqual(entry.pax_headers['SCHILY.xattr.user.fixture'], 'retained attribute')
                self.assertEqual(by_name['bin'].linkname, 'usr/bin')
                self.assertEqual(archive.extractfile(by_name['etc/systemd/system/ssh.service.d/50-image-hostkeys.conf']).read(),
                                 b'[Unit]\nRequires=image-ssh-hostkeys.service\nAfter=image-ssh-hostkeys.service\n')
            second = root / 'second.tar.xz'
            self.assertEqual(repair_tar(target, second), 0)
            self.assertEqual(inventory(target), inventory(second))

    def test_unsafe_archive_and_external_identity_directories_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / 'bad.tar.xz'
            with tarfile.open(original, 'w:xz') as archive:
                entry = tarfile.TarInfo('../outside')
                archive.addfile(entry)
            with self.assertRaisesRegex(ValueError, 'Unsafe archive'):
                repair_tar(original, root / 'safe.tar.xz')
            (root / 'etc').mkdir()
            (root / 'etc/ssh').symlink_to('/etc/ssh')
            with self.assertRaisesRegex(ValueError, 'escapes'):
                repair_directory(root)

    def test_every_refreshed_definition_finishes_with_identity_cleanup(self):
        import yaml
        root = Path(__file__).resolve().parents[2]
        for path in (root / 'images_yaml').glob('*.yaml'):
            with self.subTest(distro=path.stem):
                actions = yaml.safe_load(path.read_text())['actions']
                self.assertIn('hosted-instance-ssh-identity', actions[-1]['action'])
                self.assertNotIn('types', actions[-1])
                self.assertNotIn('variants', actions[-1])

    def test_packaged_alpine_first_boot_creates_unique_keys_then_preserves_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            binary = folder / 'bin'
            binary.mkdir()
            keygen = binary / 'ssh-keygen'
            keygen.write_text('#!/bin/sh\nexec "$REAL_KEYGEN" "$@" -f "$FIXTURE_ROOT"\n')
            keygen.chmod(0o755)
            sshd = binary / 'sshd'
            sshd.write_text('#!/bin/sh\nexit 0\n')
            sshd.chmod(0o755)
            observed = []
            for name in ('first', 'second'):
                root = folder / name
                (root / 'etc/ssh').mkdir(parents=True)
                script = '. "$INIT_SCRIPT"; start_pre'
                environment = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
                                   REAL_KEYGEN=shutil.which('ssh-keygen'), FIXTURE_ROOT=str(root),
                                   SSHD_BINARY=str(sshd), RC_SVCNAME='sshd',
                                   INIT_SCRIPT=str(Path(__file__).with_name('fixtures') / 'alpine-sshd.initd'))
                subprocess.run(['sh', '-c', script], env=environment, check=True, capture_output=True, timeout=20)
                keys = {p.name: p.read_bytes() for p in (root / 'etc/ssh').glob('ssh_host_*_key')}
                self.assertIn('ssh_host_ed25519_key', keys)
                subprocess.run(['sh', '-c', script], env=environment, check=True, capture_output=True, timeout=20)
                self.assertEqual(keys, {p.name: p.read_bytes() for p in (root / 'etc/ssh').glob('ssh_host_*_key')})
                observed.append(keys['ssh_host_ed25519_key'])
            self.assertNotEqual(*observed)

    def test_systemd_key_generation_runs_before_vendor_configuration_validation(self):
        files = runtime_files({'usr/lib/systemd/system/sshd.service', 'usr/bin/ssh-keygen'})
        self.assertIn('ExecStart=/usr/bin/ssh-keygen -A\n', files['etc/systemd/system/image-ssh-hostkeys.service'])
        self.assertIn('Requires=image-ssh-hostkeys.service', files['etc/systemd/system/sshd.service.d/50-image-hostkeys.conf'])
        self.assertEqual(runtime_files({'etc/init.d/sshd'}), {})

    def test_final_archive_gate_rejects_inherited_private_keys(self):
        from verify_image_outputs import verify
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                path = Path('fixture.tar.xz')
                with tarfile.open(path, 'w:xz') as archive:
                    entry = tarfile.TarInfo('./etc/ssh/ssh_host_fixture_key')
                    archive.addfile(entry)
                with self.assertRaisesRegex(ValueError, 'shared builder SSH'):
                    verify(path, minimum=0)
            finally:
                os.chdir(previous)

    def test_oracle_repair_targets_link_labels_and_preserves_target_attributes(self):
        import json
        import shlex
        import yaml
        from image_source_compat import NATIVE_IMAGE_ARCHIVES
        if not NATIVE_IMAGE_ARCHIVES:
            self.skipTest('Native SquashFS import repair does not alter raw archives')
        definition = yaml.safe_load((Path(__file__).resolve().parents[2] / 'images_yaml/oracle.yaml').read_text())
        hook = next(a for a in definition['actions'] if 'hosted-oracle-symlink-labels' in a['action'])
        self.assertEqual(hook['types'], ['container'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = root / 'rootfs'
            files.mkdir()
            (files / 'target').write_text('unchanged package')
            (files / 'labelled link').symlink_to('target')
            (files / 'unlabelled-link').symlink_to('target')
            binary = root / 'bin'
            binary.mkdir()
            for name in ('getfattr', 'setfattr'):
                command = binary / name
                command.write_text('#!' + sys.executable + '\nimport json,os,sys\n'
                    'with open(os.environ["CALLS"], "a") as f: f.write(json.dumps([os.path.basename(sys.argv[0]),*sys.argv[1:]])+"\\n")\n'
                    'assert sys.argv[1:5] in (["-h","-n","security.selinux","--"],["-h","-x","security.selinux","--"])\n'
                    'assert os.path.islink(sys.argv[5])\n'
                    'sys.exit(0 if sys.argv[5].endswith("labelled link") else 1)\n')
                command.chmod(0o755)
            subprocess.run(['sh', '-c', hook['action'].replace('find / -xdev', 'find ' + shlex.quote(str(files)) + ' -xdev')],
                           check=True, env=dict(os.environ, PATH=str(binary)+os.pathsep+os.environ['PATH'], CALLS=str(root/'calls')),
                           capture_output=True, timeout=10)
            calls = [json.loads(line) for line in (root/'calls').read_text().splitlines()]
            removed = [call for call in calls if call[0] == 'setfattr']
            self.assertEqual(removed, [['setfattr', '-h', '-x', 'security.selinux', '--', str(files/'labelled link')]])
            self.assertEqual((files/'target').read_text(), 'unchanged package')


if __name__ == '__main__':
    unittest.main()
