"""Ensure image builds contain no shared Gentoo SSH host keys."""
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


BASE = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).with_name('fixtures')


class GentooHostKeyTests(unittest.TestCase):
    def test_build_removes_stage_keys_without_invoking_keygen(self):
        definition = yaml.safe_load((BASE.parent / 'images_yaml/gentoo.yaml').read_text())
        hook = next(a['action'] for a in definition['actions']
                    if 'hosted-gentoo-runtime-ssh-keys' in a['action'])
        for init in ('openrc', 'systemd'):
            with self.subTest(init=init), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                ssh = root / 'etc/ssh'
                ssh.mkdir(parents=True)
                for name in ('ssh_host_fixture_key', 'ssh_host_fixture_key.pub', 'ssh_host_fixture_key-cert.pub'):
                    (ssh / name).write_text('stale build key')
                (ssh / 'sshd_config').write_text('unrelated config')
                binary = root / 'bin'
                binary.mkdir()
                for name in ('sshd', 'ssh-keygen', 'rc-update' if init == 'openrc' else 'systemctl'):
                    command = binary / name
                    command.write_text('#!/bin/sh\nprintf "%s:%s\\n" "${0##*/}" "$*" >> "$CALLS"\n'
                                       + ('exit 93\n' if name == 'ssh-keygen' else 'exit 0\n'))
                    command.chmod(0o755)
                (binary / 'rm').symlink_to(shutil.which('rm'))
                command = hook.replace('/etc/ssh/', str(ssh) + '/')
                subprocess.run([shutil.which('sh'), '-c', command], check=True, timeout=5,
                               env=dict(os.environ, PATH=str(binary), CALLS=str(root / 'calls')))
                self.assertFalse(list(ssh.glob('ssh_host_*')))
                self.assertEqual((ssh / 'sshd_config').read_text(), 'unrelated config')
                self.assertEqual((root / 'calls').read_text().splitlines(),
                                 ['rc-update:add sshd default'] if init == 'openrc' else ['systemctl:enable sshd'])

    def test_packaged_openrc_service_creates_unique_keys_and_preserves_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            keygen = folder / 'keygen'
            keygen.write_text('#!/bin/sh\nexec "${REAL_KEYGEN}" "$@" -f "$FIXTURE_ROOT"\n')
            keygen.chmod(0o755)
            sshd = folder / 'sshd'
            sshd.write_text('#!/bin/sh\nexit 0\n')
            sshd.chmod(0o755)
            observed = []
            for name in ('first-guest', 'second-guest'):
                root = folder / name
                (root / 'etc/ssh').mkdir(parents=True)
                (root / 'etc/ssh/sshd_config').write_text('Port 22\n')
                environment = dict(os.environ, RC_PREFIX=str(root), SVCNAME='sshd',
                                   SSHD_BINARY=str(sshd), SSHD_KEYGEN_BINARY=str(keygen),
                                   FIXTURE_ROOT=str(root), REAL_KEYGEN=shutil.which('ssh-keygen'),
                                   INIT_SCRIPT=str(FIXTURES / 'gentoo-sshd-r2.initd'))
                script = 'checkpath() { mkdir -p "$RC_PREFIX/var/empty"; }; . "$INIT_SCRIPT"; start_pre'
                subprocess.run(['sh', '-c', script], env=environment, check=True, capture_output=True, timeout=15)
                keys = {p.name: p.read_bytes() for p in (root / 'etc/ssh').glob('ssh_host_*_key')}
                self.assertIn('ssh_host_ed25519_key', keys)
                subprocess.run(['sh', '-c', script], env=environment, check=True, capture_output=True, timeout=15)
                self.assertEqual(keys, {p.name: p.read_bytes() for p in (root / 'etc/ssh').glob('ssh_host_*_key')})
                observed.append(keys['ssh_host_ed25519_key'])
            self.assertNotEqual(*observed)

    def test_packaged_systemd_service_generates_keys_before_starting_sshd(self):
        service = configparser.ConfigParser(interpolation=None)
        service.read(FIXTURES / 'gentoo-sshd.service.2')
        self.assertEqual(service['Service']['ExecStartPre'], '/usr/bin/ssh-keygen -A')
        self.assertIn('/usr/sbin/sshd', service['Service']['ExecStart'])
        # The retained upstream fixtures are immutable Git blobs, including
        # their original Gentoo license/copyright notices.
        import hashlib
        sources = json.loads((FIXTURES / 'gentoo-ssh-sources.json').read_text())
        for source in sources:
            payload = (FIXTURES / source['name']).read_bytes()
            actual = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
            self.assertEqual(actual, source['git_blob_sha'])


if __name__ == '__main__':
    unittest.main()
