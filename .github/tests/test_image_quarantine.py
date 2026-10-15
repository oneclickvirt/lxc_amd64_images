"""Scheduled known-broken rows are held, while manual diagnosis stays exact."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import json

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/scripts'))
from image_catalog import automatic_matrix


class AutomatedImagePolicyTests(unittest.TestCase):
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
