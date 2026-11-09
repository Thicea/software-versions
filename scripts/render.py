"""Render a standalone GitHub Pages index from the checked research data."""
import json
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def render_products(data):
    """Generate the product list from the authoritative names in versions.json."""
    products = [{'no': item['no'], 'name': item['name']} for item in data['items']]
    return json.dumps(products, ensure_ascii=False, indent=2) + '\n'


def render(data=None):
    if data is None:
        data = json.loads((ROOT / 'versions.json').read_text())
    rows = []
    for item in data['items']:
        if item['no'] in (1, 26):
            label = '■ バンドルソフト（25項目）' if item['no'] == 1 else '■ OS・ミドルウェア等（8項目）'
            rows.append(f'<tr class="section"><td colspan="5">{label}</td></tr>')
        links = ''.join(
            f'<a href="{escape(source["url"], quote=True)}" target="_blank" rel="noopener noreferrer">{escape(source["label"])}</a>'
            for source in item['sources']
        ) or '公式URL未確認（製品特定が必要）'
        values = [str(item['no']), item['name'], item['version'], item['releaseDate']]
        # A past reference must be removed from the data, never published as a current value.
        if any(marker in item['version'] for marker in ('過去参考', '過去の参考', '過去確認値', '適用済み参考値')):
            raise ValueError(f'No.{item["no"]}: 過去参考の記述・バージョンは掲載できません')
        cells = ''.join(f'<td>{escape(value)}</td>' for value in values)
        rows.append(f'<tr>{cells}<td>{links}</td></tr>')
    checked_at = '未調査'
    if data['checkedAt']:
        date = datetime.fromisoformat(data['checkedAt'].replace('Z', '+00:00'))
        if date.tzinfo is None:
            raise ValueError('調査日時にはタイムゾーンが必要です')
        date = date.astimezone(ZoneInfo('Asia/Tokyo'))
        checked_at = f'<time datetime="{date.isoformat(timespec="seconds")}">{date:%Y/%m/%d %H:%M:%S}（日本時間）</time>'
    template = (ROOT / 'templates/index.html').read_text()
    return template.replace('{{ROWS}}', '\n'.join(rows)).replace('{{CHECKED_AT}}', checked_at)


def main():
    # Validate and prepare both outputs before changing either generated file.
    from validate import validate
    data = json.loads((ROOT / 'versions.json').read_text())
    validate(data)
    html = render(data)
    products = render_products(data)
    (ROOT / 'index.html').write_text(html)
    (ROOT / 'products.json').write_text(products)
    print('versions.json から index.html と products.json を生成しました')


if __name__ == '__main__':
    main()
