"""Reject a scheduled run that changed anything except the approved fields."""
import json
import subprocess
from pathlib import Path

from refresh import immutable
from render import render
from source_support import require
from validate import validate

ROOT = Path(__file__).resolve().parents[1]


def check():
    files = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=ROOT, text=True).splitlines()
    require(set(files) <= {'versions.json', 'index.html'}, 'Scheduled update changed an unapproved file')
    previous = json.loads(subprocess.check_output(['git', 'show', 'HEAD:versions.json'], cwd=ROOT, text=True))
    current = json.loads((ROOT / 'versions.json').read_text())
    require(immutable(previous) == immutable(current), 'Product names, order, official URLs or labels changed')
    validate(current)
    require((ROOT / 'index.html').read_text() == render(current), 'Published HTML does not match the approved template/data')
    print('Scope verified: only version, releaseDate and checkedAt changed')


if __name__ == '__main__':
    check()
