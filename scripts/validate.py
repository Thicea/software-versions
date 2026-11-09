"""Validate data format without claiming factual accuracy of official sources."""
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def validate(data, products=None):
    if products is None:
        products = json.loads((ROOT / 'products.json').read_text())
    if len(data['items']) != len(products) or len(products) != 33:
        raise ValueError('全33項目が必要です')
    if data['checkedAt'] is not None:
        timestamp = datetime.fromisoformat(data['checkedAt'].replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            raise ValueError('調査日時にタイムゾーンが必要です')
    for expected, item in zip(products, data['items']):
        if (item['no'], item['name']) != (expected['no'], expected['name']):
            raise ValueError(f'製品名・順序が不正: {expected["no"]}')
        if not isinstance(item['version'], str) or not item['version'].strip():
            raise ValueError('バージョンが空です')
        date = item['releaseDate']
        if date != '未確認':
            if not re.fullmatch(r'\d{4}/\d{2}/\d{2}', date):
                raise ValueError(f'日付形式が不正: {date}')
            datetime.strptime(date, '%Y/%m/%d')
        if not isinstance(item['sources'], list) or not item['sources']:
            raise ValueError('各項目に公式参照先が必要です')
        for source in item['sources']:
            url = urlsplit(source['url'])
            if not (url.scheme == 'https' and url.hostname and not url.username and not url.password):
                raise ValueError('HTTPSの公式URLを指定してください')
            if not source['label'].strip():
                raise ValueError('リンク名が必要です')


if __name__ == '__main__':
    validate(json.loads((ROOT / 'versions.json').read_text()))
    print('OK: 全33項目、製品名・順序・日付・URL形式を確認しました（内容の正確性・公式性は手動確認が必要です）')
