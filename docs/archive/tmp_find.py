import glob
import os

os.chdir('c:/Users/sammm/Desktop/SignalRankAI')
for f in glob.glob('**/*.py', recursive=True):
    try:
        with open(f, 'r', encoding='utf-8', errors='ignore') as fh:
            if 'run_all_strategies' in fh.read():
                print(f)
    except:
        pass
