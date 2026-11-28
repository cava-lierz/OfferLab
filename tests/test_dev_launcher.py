"""Exercise the development launcher without reserving the developer's ports."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


class DevLauncherTests(unittest.TestCase):
    def test_exited_frontend_stops_backend_and_returns_its_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            scripts = root / 'scripts'
            scripts.mkdir()
            shutil.copy(Path(__file__).resolve().parents[1] / 'scripts/dev.sh', scripts)
            python = root / '.venv/bin/python'
            python.parent.mkdir(parents=True)
            python.write_text('''#!/bin/sh
if [ "$1" = -c ]; then exit 0; fi
trap 'touch backend-stopped; exit 0' TERM
touch backend-ready
while :; do sleep 0.1; done
''')
            node = python.with_name('node')
            node.write_text('''#!/bin/sh
for i in 1 2 3 4 5 6 7 8 9 10; do
  if [ -f ../backend-ready ]; then exit 7; fi
  sleep 0.1
done
exit 8
''')
            for program in (python, node):
                program.chmod(0o755)
            vite = root / 'frontend/node_modules/vite/bin/vite.js'
            vite.parent.mkdir(parents=True)
            vite.touch()
            (root / '.env').touch()
            env = dict(os.environ, PATH=str(python.parent) + os.pathsep + os.environ['PATH'])
            result = subprocess.run(['/bin/bash', scripts / 'dev.sh'], env=env,
                                    capture_output=True, text=True, timeout=8)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertTrue((root / 'backend-stopped').is_file())
