"""Scheduled known-broken rows are held, while manual diagnosis stays exact."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import json
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/scripts'))
from image_catalog import automatic_matrix


class AutomatedImagePolicyTests(unittest.TestCase):
    def test_upstream_refresh_dispatch_preserves_automatic_quarantine(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/clone_yaml.yml').read_text())
        step = next(item for item in workflow['jobs']['clone_yaml']['steps']
                    if item.get('name') == 'Commit validated source snapshot')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            def git(*args):
                return subprocess.run(['git', *args], cwd=folder, check=True,
                                      capture_output=True, text=True)
            git('init', '-q')
            git('config', 'user.name', 'fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (folder / 'images_yaml').mkdir()
            (folder / '.github/scripts').mkdir(parents=True)
            (folder / 'images_yaml/fixture.yaml').write_text('old definition\n')
            (folder / 'all_images.txt').write_text('fixture\n')
            (folder / '.github/image-catalog.json').write_text('{}\n')
            (folder / '.github/scripts/ci_network.sh').write_text(
                'ci_retry() { printf "%s\\n" "$*" >> "$DISPATCH_CALLS"; }\n')
            (folder / '.github/scripts/push_image_snapshot.py').write_text('pass\n')
            (folder / 'image-definition-check/bin').mkdir(parents=True)
            (folder / 'image-definition-check/bin/python').symlink_to(sys.executable)
            git('add', '.')
            git('commit', '-qm', 'baseline')
            (folder / 'images_yaml/fixture.yaml').write_text('new definition\n')
            calls = folder / 'calls'
            environment = dict(os.environ, RUNNER_TEMP=str(folder), BUILD_IMAGES='true',
                               GITHUB_REPOSITORY='oneclickvirt/' + ROOT.name,
                               GITHUB_REF_NAME='main', DISPATCH_CALLS=str(calls))
            subprocess.run(['bash', '-c', step['run']], cwd=folder, env=environment,
                           check=True, capture_output=True, timeout=15)
            dispatches = calls.read_text().splitlines()
            self.assertEqual(len(dispatches), 1 if ROOT.name.startswith('lxc_') else 2)
            self.assertTrue(all('--field automatic=true' in call for call in dispatches))
            self.assertTrue(all('workflow run hosted-build.yml' in call for call in dispatches))

    def test_only_the_exact_failed_architecture_and_kind_are_quarantined(self):
        rows = [{'distro': 'debian', 'release': 'trixie', 'arch': arch, 'kind': kind}
                for arch in ['amd64', 'arm64'] for kind in ['container', 'vm']]
        entry = dict(rows[-1], reason='Confirmed boot failure; manual repair available',
                     evidence='https://github.com/oneclickvirt/incus_images/actions/runs/123')
        selected = automatic_matrix({'include': rows}, {'schema': 1, 'entries': [entry]})
        self.assertEqual(selected['include'], rows[:-1])
        self.assertEqual(rows[-1]['arch'], 'arm64')
        with self.assertRaises(ValueError):
            automatic_matrix({'include': rows}, {'schema': 1, 'entries': [entry, entry]})

    def test_manual_can_repair_quarantine_and_an_empty_schedule_skips_builds(self):
        repo = ROOT.name
        arch = 'arm64' if repo == 'lxc_arm_images' else 'amd64'
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / '.github').mkdir()
            catalog = {'schema': 1, 'source_commit': 'a' * 40, 'distros': {}}
            from image_catalog import DISTROS
            for name in DISTROS:
                catalog['distros'][name] = {'releases': [{'release': 'fixture', 'version': 'fixture'}],
                                           'architectures': [arch], 'variants': ['default']}
            (folder / '.github/image-catalog.json').write_text(json.dumps(catalog))
            entry = {'distro': 'debian', 'release': 'fixture', 'arch': arch, 'kind': 'container',
                     'reason': 'Fixture boot regression',
                     'evidence': 'https://github.com/oneclickvirt/' + repo + '/actions/runs/123'}
            (folder / '.github/image-build-quarantine.json').write_text(json.dumps({'schema': 1, 'entries': [entry]}))
            output = folder / 'output'
            command = [sys.executable, str(ROOT / '.github/scripts/image_catalog.py'), 'matrix', '--distro', 'debian', '--arch', arch]
            environment = dict(os.environ, GITHUB_REPOSITORY='oneclickvirt/' + repo,
                               GITHUB_OUTPUT=str(output), CI_IMAGE_AUTOMATIC='true')
            subprocess.run(command, cwd=folder, env=environment, check=True, capture_output=True, timeout=10)
            self.assertIn('count=0', output.read_text())
            self.assertIn('matrix={"include":[]}', output.read_text())
            output.unlink()
            environment['CI_IMAGE_AUTOMATIC'] = 'false'
            subprocess.run(command, cwd=folder, env=environment, check=True, capture_output=True, timeout=10)
            self.assertIn('count=1', output.read_text())
            self.assertIn('"release":"fixture"', output.read_text())
        workflow = (ROOT / '.github/workflows/hosted-build.yml').read_text()
        self.assertIn("if: needs.catalog.outputs.count != '0'", workflow)


if __name__ == '__main__':
    unittest.main()
