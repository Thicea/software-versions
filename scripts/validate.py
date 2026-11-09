"""Validate the published data without claiming its factual accuracy."""
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[1]
products = json.loads((root / 'products.json').read_text())
data = json.loads((root / 'versions.json').read_text())
assert len(data['items']) == len(products) == 33, '全33項目が必要です'
if data['checkedAt'] is not None:
    timestamp = datetime.fromisoformat(data['checkedAt'].replace('Z', '+00:00'))
    assert timestamp.tzinfo is not None, '調査日時にタイムゾーンが必要です'
for expected, item in zip(products, data['items']):
    assert (item['no'], item['name']) == (expected['no'], expected['name']), f'製品名・順序が不正: {expected["no"]}'
    assert isinstance(item['version'], str) and item['version'].strip(), 'バージョンが空です'
    date = item['releaseDate']
    if date != '未確認':
        assert re.fullmatch(r'\d{4}/\d{2}/\d{2}', date), f'日付形式が不正: {date}'
        datetime.strptime(date, '%Y/%m/%d')
    assert isinstance(item['sources'], list), 'sourcesは配列です'
    assert item['sources'] or item['version'] in ('今回未確認', '最新版未確定'), '確定した項目には公式URLが必要です'
    for source in item['sources']:
        url = urlsplit(source['url'])
        assert url.scheme == 'https' and url.hostname and not url.username and not url.password, 'HTTPSの公式URLを指定してください'
        assert source['label'].strip(), 'リンク名が必要です'
print('OK: 全33項目、製品名・順序・日付・URL形式を確認しました（内容の正確性・公式性は手動確認が必要です）')
