"""Exercise real subprocess failures and partial output recovery."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '.github/scripts/build_image_retry.py'


class SourceRecoveryTests(unittest.TestCase):
    def execute(self, body):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            builder = root / 'builder.py'
            builder.write_text('from pathlib import Path\nimport sys, os\n' + body)
            command = [sys.executable, '-c',
                       'import importlib.util,sys; s=importlib.util.spec_from_file_location("retry",sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); sys.exit(m.build([sys.executable,sys.argv[2]],budget=10,delay=0))',
                       str(SCRIPT), str(builder)]
            value = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=15,
                                   env=dict(os.environ, GH_TOKEN='fixture-secret', GITHUB_TOKEN='fixture-secret'))
            return value, (root / 'calls').read_text(), (root / 'disk.qcow2').read_bytes() if (root / 'disk.qcow2').exists() else None

    def test_transient_bootstrap_download_retries_once_and_clears_partial_output(self):
        value, calls, output = self.execute('''p=Path('calls'); count=len(p.read_text()) if p.exists() else 0
p.write_text('x'*(count+1))
assert 'GH_TOKEN' not in os.environ and 'GITHUB_TOKEN' not in os.environ
if count==0:
 Path('disk.qcow2').write_bytes(b'partial')
 print("E: Couldn't download packages: libseccomp2")
 sys.exit(17)
assert not Path('disk.qcow2').exists()
Path('disk.qcow2').write_bytes(b'complete')
''')
        self.assertEqual(value.returncode, 0, value.stderr)
        self.assertEqual(calls, 'xx')
        self.assertEqual(output, b'complete')

    def test_compile_and_signature_failures_do_not_retry(self):
        for message in ['compile hook failed', "E: Couldn't download packages: GPG check FAILED"]:
            value, calls, _ = self.execute('Path("calls").write_text("x")\nprint('+repr(message)+')\nsys.exit(17)\n')
            self.assertEqual(value.returncode, 17, value.stderr)
            self.assertEqual(calls, 'x')

    def test_stuck_builder_is_terminated_without_resetting_the_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            builder = root / 'stuck.py'
            builder.write_text('from pathlib import Path; import time; Path("calls").write_text("x"); time.sleep(20)')
            command = [sys.executable, '-c',
                       'import importlib.util,sys; s=importlib.util.spec_from_file_location("retry",sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); sys.exit(m.build([sys.executable,sys.argv[2]],budget=0.5,delay=0))',
                       str(SCRIPT), str(builder)]
            value = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=5)
            self.assertEqual(value.returncode, 124, value.stderr)
            self.assertEqual((root / 'calls').read_text(), 'x')
            self.assertIn('bounded budget', value.stderr)

    def test_persistent_download_failure_stops_after_two_attempts(self):
        value, calls, _ = self.execute('p=Path("calls"); p.write_text((p.read_text() if p.exists() else "")+"x")\nprint("E: Couldn\'t download packages: fixture")\nsys.exit(17)\n')
        self.assertEqual(value.returncode, 17, value.stderr)
        self.assertEqual(calls, 'xx')

    def test_exited_builder_cannot_leave_a_child_holding_output_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            builder = root / 'fork.py'
            builder.write_text('import subprocess,sys\nsubprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])\n')
            command = [sys.executable, '-c',
                       'import importlib.util,sys; s=importlib.util.spec_from_file_location("retry",sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); sys.exit(m.build([sys.executable,sys.argv[2]],budget=0.5,delay=0))',
                       str(SCRIPT), str(builder)]
            value = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=5)
            self.assertEqual(value.returncode, 124, value.stderr)
            self.assertIn('bounded budget', value.stderr)


if __name__ == '__main__':
    unittest.main()
