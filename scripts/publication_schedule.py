"""Warm up early, investigate at 08:30 JST and request publication near 08:40."""
import sys
import time
from datetime import datetime, time as day_time
from zoneinfo import ZoneInfo

JST = ZoneInfo('Asia/Tokyo')
RESEARCH_TIME = day_time(8, 30)
PUBLISH_TIME = day_time(8, 38)  # Leave about two minutes for Pages build/CDN propagation.


def wait_for_stage(stage, event, clock=None, sleeper=None):
    if event != 'schedule':
        return True
    clock = clock or (lambda: datetime.now(JST))
    sleeper = sleeper or time.sleep
    now = clock().astimezone(JST)
    if now.weekday() >= 5:
        return False
    target = datetime.combine(now.date(), {'research': RESEARCH_TIME, 'publish': PUBLISH_TIME}[stage], JST)
    print(f'{stage}: target {target.isoformat()}; current {now.isoformat()}', file=sys.stderr, flush=True)
    while now < target:
        sleeper(min(60, (target - now).total_seconds()))
        now = clock().astimezone(JST)
        if now.date() != target.date():
            raise ValueError('The preparation crossed a JST day; do not publish an earlier investigation')
    return True


def verify_today(data, now, scheduled=False):
    now = now.astimezone(JST)
    checked = datetime.fromisoformat((data['checkedAt'] or '').replace('Z', '+00:00'))
    if checked.tzinfo is None or checked > now:
        raise ValueError('Invalid/future research timestamp')
    checked = checked.astimezone(JST)
    if checked.date() != now.date():
        raise ValueError('Previous-day research cannot be published as today\'s update')
    if scheduled and checked.time() < RESEARCH_TIME:
        raise ValueError('Morning publication requires fresh research at or after 08:30 JST')
