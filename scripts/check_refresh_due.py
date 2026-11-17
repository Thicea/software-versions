"""Avoid duplicate research when a delayed schedule or recovery trigger arrives."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from validate import validate
from publication_schedule import RESEARCH_TIME, wait_for_stage, verify_today

ROOT = Path(__file__).resolve().parents[1]
JST = ZoneInfo('Asia/Tokyo')
MORNING_START = RESEARCH_TIME


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
    parser.add_argument('--wait', choices=['research', 'publish'])
    parser.add_argument('--verify-today', action='store_true')
    args = parser.parse_args()
    if args.wait:
        eligible = wait_for_stage(args.wait, args.event)
        if args.wait == 'research':
            print('eligible=' + str(eligible).lower())
        return
    data = json.loads((ROOT / 'versions.json').read_text())
    validate(data)
    if args.verify_today:
        verify_today(data, datetime.now(JST), scheduled=args.event == 'schedule')
        print('Verified: research is from today in Japan')
        return
    # Manual/configuration verification runs investigate immediately, including at night.
    due = args.event != 'schedule' or research_due(data, datetime.now(JST))
    print('due=' + str(due).lower())
    print('Fresh research required' if due else 'Research already completed for this morning, or outside its weekday window', file=sys.stderr)


if __name__ == '__main__':
    main()
