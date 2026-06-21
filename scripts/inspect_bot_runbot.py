import sys
import os
import inspect

# Ensure repo root is on sys.path so local package imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import signalrank_telegram.bot as b

src = inspect.getsource(b.run_bot)
print('COALESCE IN SOURCE:', 'coalesce' in src)
print('MISFIRE IN SOURCE:', 'misfire_grace_time' in src)
print(src.find('coalesce'))
print(src.find('misfire_grace_time'))

print('run_bot file:', inspect.getsourcefile(b.run_bot))
print('run_bot firstlineno:', getattr(b.run_bot, '__code__', None).co_firstlineno)
print('source length:', len(src))
print('job_defaults in src:', 'job_defaults' in src)
idx = src.find('job_defaults')
print('job_defaults index:', idx)
if idx != -1:
	print('snippet around job_defaults:')
	print(src[idx:idx+200])
