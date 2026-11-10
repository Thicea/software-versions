"""Avoid duplicate research when a delayed schedule or recovery trigger arrives."""
import argparse
import json
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from validate import validate

ROOT = Path(__file__).resolve().parents[1]
JST = ZoneInfo('Asia/Tokyo')
MORNING_START = time(8, 15)


def research_due(data, now):
    if now.tzinfo is None:
        raise ValueError('Current time must include a timezone')
    now = now.astimezone(JST)
    if now.weekday() >= 5 or now.time() < MORNING_START:
        return False
    if not data['checkedAt']:
        return True
    checked = datetime.fromisoformat(data['checkedAt'].replace('Z', '+00:00'))
    if checked.tzinfo is None or checked > now:
        raise ValueError('Research timestamp must be timezone-aware and not in the future')
    checked = checked.astimezone(JST)
    return checked.date() != now.date() or checked.time() < MORNING_START


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', choices=['schedule', 'push', 'workflow_dispatch'], required=True)
    args = parser.parse_args()
    data = json.loads((ROOT / 'versions.json').read_text())
    validate(data)
    # Manual dispatch explicitly requests a fresh investigation, even if already done.
    due = args.event == 'workflow_dispatch' or research_due(data, datetime.now(JST))
    print('due=' + str(due).lower())
    print('Fresh research required' if due else 'Research already completed for this morning, or outside its weekday window', file=sys.stderr)


if __name__ == '__main__':
    main()
