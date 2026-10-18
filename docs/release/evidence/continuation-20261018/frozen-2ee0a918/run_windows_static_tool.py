import os
from pathlib import Path
import runpy
import sys
import sysconfig

if sysconfig.get_platform() != 'win-amd64':
    raise SystemExit('This local launcher requires verified win-amd64 Python')
if len(sys.argv) < 2 or sys.argv[1] not in {'scripts.install_opengrep', 'scripts.semgrep_gate', 'pip_audit'}:
    raise SystemExit('Only the named static-security tools are supported')
module = sys.argv.pop(1)
os.environ['PROCESSOR_ARCHITECTURE'] = 'AMD64'
runpy.run_module(module, run_name='__main__')
