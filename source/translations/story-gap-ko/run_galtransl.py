"""Run GalTransl on the story-gap project with the shared runner (galtransl skill).

The shared runner lives in ~/.claude/skills/galtransl/scripts/run_galtransl.py: it starts the GalTransl 8.5.0 backend
(D:/Util), injects the LiteLLM gateway key into a temporary config.runtime.yaml when config.yaml has the GATEWAY_KEY
placeholder, opens the Mac mini tunnel if needed, and waits for the job.

usage: python -I translations/story-gap-ko/run_galtransl.py [--project build/out/story_gap_gt] [--translator ForGal-markdown]
"""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARED = Path.home() / '.claude' / 'skills' / 'galtransl' / 'scripts' / 'run_galtransl.py'

if __name__ == '__main__':
    args = sys.argv[1:]
    if '--project' not in args:
        args = ['--project', str(ROOT / 'build/out/story_gap_gt')] + args
    if not SHARED.exists():
        sys.exit('shared runner not found: ' + str(SHARED))
    sys.exit(subprocess.call([sys.executable, '-I', str(SHARED)] + args))
