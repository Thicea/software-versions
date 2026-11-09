"""Restrict research updates and rendering to their respective approved files."""
import argparse
import json
import subprocess
from pathlib import Path

from refresh import immutable
from render import render, render_products
from source_support import require
from validate import validate

ROOT = Path(__file__).resolve().parents[1]


def check(generated_only=False):
    files = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=ROOT, text=True).splitlines()
    allowed = {'products.json', 'index.html'} if generated_only else {'versions.json', 'index.html'}
    require(set(files) <= allowed, 'Update changed an unapproved file')
    previous = json.loads(subprocess.check_output(['git', 'show', 'HEAD:versions.json'], cwd=ROOT, text=True))
    current = json.loads((ROOT / 'versions.json').read_text())
    if generated_only:
        require(previous == current, 'Rendering must not change versions.json or the research timestamp')
    else:
        require(immutable(previous) == immutable(current), 'Product names, order, official URLs or labels changed')
    validate(current)
    require((ROOT / 'index.html').read_text() == render(current), 'Published HTML does not match the approved template/data')
    require((ROOT / 'products.json').read_text() == render_products(current), 'Product list does not match versions.json')
    print('Scope verified: ' + ('only generated HTML/product list changed' if generated_only
                                else 'only version, releaseDate and checkedAt changed'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generated-only', action='store_true', help='Allow only generated index.html/products.json changes')
    check(parser.parse_args().generated_only)
