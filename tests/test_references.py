import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from references import article_reference, validate_reference_versions
from research_sources import github_release, sql, SQL
from refresh import immutable, prepare_update
from source_support import Document, SourceError
from validate import validate

ROOT = Path(__file__).resolve().parents[1]


class Pages:
    def __init__(self, pages):
        self.pages = pages
        self.evidence = {}

    def doc(self, url):
        if url not in self.pages:
            raise SourceError('Translation unavailable')
        self.evidence[url] = {'finalUrl': url}
        return Document(self.pages[url])


class ReferenceTests(unittest.TestCase):
    def test_matching_japanese_article_is_preferred(self):
        en = 'https://support.microsoft.com/en-us/help/5999999'
        ja = en.replace('/en-us/', '/ja-jp/')
        client = Pages({ja: '<html lang="ja-JP"><h1>2026 年 11 月 10 日 KB5999999 OS ビルド 20348.9000</h1></html>'})
        self.assertEqual(article_reference(client, en, 'KB', 'KB5999999', '20348.9000', '2026/11/10')['url'], ja)

    def test_missing_or_stale_japanese_article_falls_back_to_verified_original(self):
        en = 'https://support.microsoft.com/en-us/help/5999999'
        ja = en.replace('/en-us/', '/ja-jp/')
        for pages in ({}, {ja: '<html lang="ja"><h1>KB5999999</h1>20348.8000 2026 年 10 月 13 日</html>'},
                      {ja: '<html lang="en"><h1>KB5999999 20348.9000</h1></html>'}):
            with self.subTest(pages=pages):
                self.assertEqual(article_reference(Pages(pages), en, 'KB', 'KB5999999', '20348.9000', '2026/11/10')['url'], en)

    def test_release_link_is_the_actual_selected_tag(self):
        url = 'https://github.com/TeraTermProject/teraterm/releases'
        html = '<section id="release-v5.9.1"><h2>5.9.1</h2><a href="/TeraTermProject/teraterm/releases/tag/v5.9.1">Release</a><relative-time datetime="2026-11-10T00:00:00Z"></relative-time></section>'
        value = github_release(Pages({url: html}), 'TeraTermProject/teraterm', date(2026, 11, 18), '公式リリース')
        self.assertEqual(value['sources'][0]['url'], url + '/tag/v5.9.1')

    def test_new_cu_without_its_own_gdr_drops_the_old_security_article(self):
        table = '''SQL Server 2022<table><tr><th>Cumulative update name</th><th>SQL Server build version</th><th>Knowledge Base number</th><th>Release date</th></tr>
        <tr><td>CU28</td><td>16.0.4400.1</td><td>KB5999998</td><td>November 10, 2026</td></tr>
        <tr><td>CU27 + GDR</td><td>16.0.4305.5</td><td>KB5999997</td><td>October 13, 2026</td></tr>
        <tr><td>GDR</td><td>16.0.1220.3</td><td>KB5999996</td><td>November 10, 2026</td></tr></table>'''
        pages = {SQL: table}
        for kb, version in [('5999998', '16.0.4400.1'), ('5999996', '16.0.1220.3')]:
            pages['https://support.microsoft.com/en-us/help/' + kb] = f'<h1>KB{kb}</h1><p>Release date: November 10, 2026 Version: {version}</p>'
        value = sql(Pages(pages), date(2026, 11, 18))
        self.assertIn('該当更新なし', value[30]['version'])
        self.assertEqual(len(value[30]['sources']), 1)
        self.assertEqual(value[30]['sources'][0]['url'], SQL.replace('/en-us/', '/ja-jp/'))
        self.assertIn('5999998', value[29]['sources'][0]['url'])

    def test_stale_release_tag_and_kb_links_are_rejected(self):
        for item in [
            {'no': 12, 'version': '2.42.0', 'sources': [{'url': 'https://github.com/aws/aws-cli/releases/tag/2.39.6'}]},
            {'no': 26, 'version': 'KB5999999', 'sources': [{'url': 'https://support.microsoft.com/en-us/help/5888888'}]},
        ]:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_reference_versions({'items': [item]})

    def test_framework_reference_cannot_be_a_mixed_update_history(self):
        item = {'no': 33, 'version': 'KB5999999（Windows Server 2022向け.NET Framework 3.5／4.8）',
                'sources': [{'url': 'https://support.microsoft.com/ja-jp/servicing/dotnetframework/microsoft-server/2022/history'}]}
        with self.assertRaises(ValueError):
            validate_reference_versions({'items': [item]})

    def test_only_approved_reference_changes_are_accepted(self):
        previous = json.loads((ROOT / 'versions.json').read_text())
        results = {i['no']: {key: i[key] for key in ('version', 'releaseDate')} for i in previous['items']}
        results[1]['sources'] = [{'label': '公式更新情報', 'url': 'https://learn.microsoft.com/ja-jp/cpp/windows/latest-supported-vc-redist'}]
        current = prepare_update(previous, results, '2026-11-18T08:31:00+09:00')
        self.assertEqual(immutable(previous), immutable(current))
        self.assertEqual(current['items'][0]['sources'], results[1]['sources'])
        results[1]['name'] = 'Different product'
        with self.assertRaises(SourceError):
            prepare_update(previous, results, '2026-11-18T08:31:00+09:00')

    def test_direct_downloads_and_ssm_github_references_are_rejected(self):
        base = json.loads((ROOT / 'versions.json').read_text())
        for no, url in [(1, 'https://download.microsoft.com/setup.exe'), (11, 'https://github.com/aws/amazon-ssm-agent/releases')]:
            changed = copy.deepcopy(base)
            changed['items'][no-1]['sources'] = [{'label': 'Forbidden', 'url': url}]
            with self.subTest(no=no), self.assertRaises(ValueError):
                validate(changed)


if __name__ == '__main__':
    unittest.main()
