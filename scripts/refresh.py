"""Refresh only versions, formal release dates, and the fixed JST research time."""
import argparse
import copy
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from render import render
from research_sources import COLLECTORS
from source_support import Client, require
from validate import validate

ROOT = Path(__file__).resolve().parents[1]


def immutable(data):
    frozen = copy.deepcopy(data)
    frozen.pop('checkedAt', None)
    for item in frozen['items']:
        item.pop('version', None)
        item.pop('releaseDate', None)
    return frozen


def prepare_update(previous, results, checked_at):
    require(set(results) == set(range(1, 34)), 'Exactly 33 fresh checks are required')
    updated = copy.deepcopy(previous)
    for item in updated['items']:
        changes = results[item['no']]
        require(set(changes) == {'version', 'releaseDate'}, 'Only version/releaseDate may be updated')
        item.update(changes)
    updated['checkedAt'] = checked_at
    require(immutable(updated) == immutable(previous), 'Product names, order, official URLs or labels changed')
    validate(updated)
    return updated


def refresh(previous, client, now=None):
    now = now or datetime.now(ZoneInfo('Asia/Tokyo'))
    results, failures = {}, []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fn, client, now.date()): fn.__name__ for fn in COLLECTORS}
        for future in as_completed(futures):
            name = futures[future]
            try:
                values = future.result()
                require(not set(values).intersection(results), 'Duplicate product check')
                results.update(values)
                print(f'OK {name}: ' + ', '.join(str(n) for n in values), flush=True)
            except Exception as error:
                failures.append({'collector': name, 'error': f'{type(error).__name__}: {error}'})
                print(f'FAILED {name}: {type(error).__name__}: {error}', flush=True)
    report = {'startedAt': now.isoformat(timespec='seconds'),
              'sources': sorted(client.evidence.values(), key=lambda s: s['url']),
              'failures': failures, 'items': results}
    # No fresh timestamp or files are published if even one collector failed.
    if failures:
        return None, report
    checked_at = datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(timespec='seconds')
    updated = prepare_update(previous, results, checked_at)
    report['checkedAt'] = checked_at
    report['uncertainItems'] = [item['no'] for item in updated['items'] if '最新版未確定' in item['version']]
    return updated, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Fetch/validate, but do not modify the website')
    parser.add_argument('--report', type=Path, required=True, help='Run-local evidence JSON (outside the checkout)')
    args = parser.parse_args()
    require(not args.report.resolve().is_relative_to(ROOT), 'Research report must be outside the checkout')
    previous = json.loads((ROOT / 'versions.json').read_text())
    validate(previous)
    updated, report = refresh(previous, Client())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if updated is None:
        raise SystemExit('Fresh official-source checks failed; website files and research timestamp were preserved')
    html = render(updated)
    if not args.dry_run:
        (ROOT / 'versions.json').write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n')
        (ROOT / 'index.html').write_text(html)
    print(f'All 33 checks complete; JST {updated["checkedAt"]}; uncertain items {report["uncertainItems"]}; dry_run={args.dry_run}')


if __name__ == '__main__':
    main()
