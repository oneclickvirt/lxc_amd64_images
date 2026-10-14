"""Use a real local Git remote to reproduce concurrent refresh publication."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import push_image_snapshot as snapshot
from image_catalog import DISTROS


class SnapshotPushTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.remote = self.root / 'remote.git'
        self.git(self.root, 'init', '--bare', str(self.remote))
        seed = self.root / 'seed'
        seed.mkdir()
        self.git(seed, 'init', '-b', 'main')
        self.identity(seed)
        (seed / 'images_yaml').mkdir()
        (seed / '.github').mkdir()
        definition = 'image:\n  distribution: fixture\nsource:\n  downloader: fixture\nactions: []\n'
        for name in DISTROS:
            (seed / 'images_yaml' / (name+'.yaml')).write_text(definition)
        catalog = {'schema':1, 'source_commit':'a'*40, 'distros':{
            name:{'releases':[{'release':'current','version':'current'}], 'architectures':['amd64'], 'variants':['default']}
            for name in DISTROS}}
        (seed / '.github/image-catalog.json').write_text(json.dumps(catalog))
        (seed / 'all_images.txt').write_text('previous image\n')
        (seed / 'README.md').write_text('previous maintenance\n')
        self.commit(seed, 'baseline')
        self.git(seed, 'remote', 'add', 'origin', str(self.remote))
        self.git(seed, 'push', 'origin', 'main')
        for name in ('runner','maintainer'):
            target = self.root / name
            self.git(self.root, 'clone', '--branch', 'main', str(self.remote), str(target))
            self.identity(target)
        self.runner = self.root / 'runner'
        self.maintainer = self.root / 'maintainer'
        (self.runner / 'all_images.txt').write_text('fresh image\n')
        self.commit(self.runner, 'fresh snapshot')

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def git(root, *arguments):
        return subprocess.run(['git', *arguments], cwd=root, check=True, text=True, capture_output=True)

    def identity(self, root):
        self.git(root, 'config', 'user.name', 'fixture')
        self.git(root, 'config', 'user.email', 'fixture@example.invalid')

    def commit(self, root, message):
        self.git(root, 'add', '.')
        self.git(root, 'commit', '-m', message)

    def test_concurrent_maintenance_and_fresh_index_both_survive(self):
        (self.maintainer / 'README.md').write_text('concurrent maintenance\n')
        self.commit(self.maintainer, 'maintainer change')
        self.git(self.maintainer, 'push', 'origin', 'main')
        snapshot.publish(self.runner, 'main')
        self.assertEqual(self.git(self.remote, 'show', 'main:README.md').stdout, 'concurrent maintenance\n')
        self.assertEqual(self.git(self.remote, 'show', 'main:all_images.txt').stdout, 'fresh image\n')

    def test_conflicting_refresh_keeps_remote_commit_and_aborts_rebase(self):
        (self.maintainer / 'all_images.txt').write_text('concurrent image\n')
        self.commit(self.maintainer, 'concurrent refresh')
        self.git(self.maintainer, 'push', 'origin', 'main')
        remote_before = self.git(self.remote, 'rev-parse', 'main').stdout
        with self.assertRaisesRegex(RuntimeError, 'changes conflict'):
            snapshot.publish(self.runner, 'main')
        self.assertEqual(self.git(self.remote, 'rev-parse', 'main').stdout, remote_before)
        self.assertFalse((self.runner / '.git/rebase-merge').exists())
        self.assertFalse(self.git(self.runner, 'status', '--porcelain').stdout)

    def test_lost_push_response_is_reconciled_without_another_commit(self):
        original = subprocess.run
        lost = False

        def execute(command, **kwargs):
            nonlocal lost
            result = original(command, **kwargs)
            if command[1] == 'push' and not lost:
                lost = True
                self.assertEqual(result.returncode, 0)
                result.returncode = 1
            return result

        before = self.git(self.runner, 'rev-parse', 'HEAD').stdout
        with mock.patch.object(snapshot.subprocess, 'run', side_effect=execute):
            snapshot.publish(self.runner, 'main')
        self.assertEqual(self.git(self.remote, 'rev-parse', 'main').stdout, before)
        self.assertEqual(self.git(self.runner, 'rev-parse', 'HEAD').stdout, before)


if __name__ == '__main__':
    unittest.main()
