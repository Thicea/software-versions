import copy
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from source_support import Document, SourceError, https_url
from research_sources import (aws_table, cfn_result, edge, framework, github_release,
                              numbered_notes, select_sql, sql_records)
from refresh import immutable, prepare_update
from publish_pages import check_build, wait_for_build
import refresh

TODAY = date(2026, 11, 9)
ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self, html=None, metadata=None):
        self.html = html or {}
        self.metadata = metadata or {}

    def doc(self, url):
        return Document(self.html[url] if isinstance(self.html, dict) else self.html)

    def json(self, url):
        return self.metadata


class ReleaseSelectionTests(unittest.TestCase):
    def test_driver_series_and_ancient_formats(self):
        doc = Document('''<h2>18.9</h2><p>Version number: 18.9.1.1 Released: November 1, 2026</p>
          <h2>17.11</h2><p>Version number: 17.11.1.1<br>Released: April 30, 2026</p>
          <h2>17.4.2</h2><p>Ancient date layout</p>''')
        self.assertEqual(numbered_notes(doc, 17, TODAY)['version'], '17.11.1.1')

    def test_missing_latest_date_does_not_fall_back(self):
        doc = Document('''<h2>18.7.6</h2><p>Date unknown</p><h2>18.7.5</h2>
          <p>Released: May 9, 2025</p>''')
        with self.assertRaises(SourceError):
            numbered_notes(doc, 18, TODAY)

    def test_ssms_later_major_is_excluded_and_build_is_required(self):
        doc = Document('''<h2>21.1.0</h2><p>Release date: November 1, 2026</p>
          <h2>20.2.1</h2><p>Release number: 20.2.1 Build number: 20.2.37.0 Release date: April 8, 2025</p>''')
        self.assertEqual(numbered_notes(doc, 20, TODAY, True)['version'], '20.2.1（ビルド 20.2.37.0）')
        with self.assertRaises(SourceError):
            numbered_notes(Document('<h2>20.3.0</h2><p>Release date: November 1, 2026</p>'), 20, TODAY, True)

    def test_aws_latest_row_ignores_older_empty_date(self):
        doc = Document('''<table><tr><th>Package version</th><th>Details</th><th>Release date</th></tr>
          <tr><td>8.6.1</td><td>Fix</td><td>July 21, 2026</td></tr>
          <tr><td>8.0.0</td><td>Old</td><td></td></tr></table>''')
        self.assertEqual(aws_table(doc, TODAY)['releaseDate'], '2026/07/21')

    def test_cfn_disagreement_is_retained_without_regional_claims(self):
        same = {'version': '2.0-42', 'releaseDate': '2026/10/20'}
        old = {'version': '2.0-41', 'releaseDate': '2026/09/24'}
        value = cfn_result([same, same, old])
        self.assertIn('日本語は2.0-41', value['version'])
        self.assertEqual(value['releaseDate'], '2026/10/20')
        self.assertIn('最新版未確定', cfn_result([old, same, old])['version'])

    def test_github_preview_numeric_version_is_not_a_stable_release(self):
        html = '''<section id="release-v14.1.0"><h2>[14.1.0] Preview Release</h2>
          <a href="/microsoft/mssql-jdbc/releases/tag/v14.1.0">14.1.0</a><relative-time datetime="2026-11-01T00:00:00Z"></relative-time></section>
          <section id="release-v13.6.2"><h2>[13.6.2] Hotfix &amp; Stable Release</h2>
          <a href="/microsoft/mssql-jdbc/releases/tag/v13.6.2">13.6.2</a><relative-time datetime="2026-11-02T08:38:29Z"></relative-time></section>'''
        self.assertEqual(github_release(Client(html), 'microsoft/mssql-jdbc', TODAY), {'version': '13.6.2', 'releaseDate': '2026/11/02'})

    def test_edge_extended_stable_is_excluded(self):
        html = '''<h2>Version 158.0.9999.99: November 5, 2026 (Extended Stable)</h2>
          <h2>Version 157.0.4341.42: November 05, 2026 (Stable) - Main Release</h2>'''
        self.assertEqual(edge(Client(html), TODAY)[28]['version'], '157.0.4341.42（Stable）')

    def test_new_cu_has_no_security_update_cannot_reuse_previous_cu_gdr(self):
        records = [('CU28', 'KB5999999', '16.0.4400.1', '2026/11/09'),
                   ('CU27 + GDR', 'KB5126934', '16.0.4305.5', '2026/10/13'),
                   ('GDR', 'KB5128493', '16.0.1210.3', '2026/10/13')]
        cu, cu_gdr, gdr = select_sql(records)
        self.assertEqual(cu[0], 'CU28')
        self.assertIsNone(cu_gdr)
        self.assertEqual(gdr[1], 'KB5128493')

    def test_sql_engine_version_does_not_use_analysis_services_build(self):
        doc = Document('''<table><tr><th>Cumulative update name</th><th>SQL Server build version</th>
          <th>Analysis Services build version</th><th>Knowledge Base number</th><th>Release date</th></tr>
          <tr><td>CU27 (Latest)</td><td>16.0.4295.3</td><td>16.0.43.252</td><td>KB5104824</td><td>September 15, 2026</td></tr></table>''')
        self.assertEqual(sql_records(doc, TODAY)[0][2], '16.0.4295.3')

    def test_framework_48_specific_kb_ignores_sidebar_and_481(self):
        base = 'https://support.microsoft.com/en-us/servicing/dotnetframework/microsoft-server/2022/'
        history = base+'2021/09/history-of-cumulative-updates-for-net-framework-for-windows-server-2022'
        summary = base+'2026/10/summary'
        article = base+'2026/10/kb5127687'
        client = Client({history: '<main>Framework</main>',
                         summary: '''<aside><li><a href="old">5000000</a> .NET Framework 3.5 and 4.8 for Windows Server 2022</li></aside>
                         <main><ul><li><a href="kb5127687">5127687</a> Description of .NET Framework 3.5 and 4.8 for Windows Server 2022</li>
                         <li><a href="kb5127693">5127693</a> Description of .NET Framework 3.5 and 4.8.1 for Windows Server 2022</li></ul></main>''',
                         article: '<h1>KB5127687 .NET Framework 3.5 and 4.8 for Windows Server 2022</h1><p>Release Date: October 13, 2026</p>'},
                        {'items': [{'href': '2026/10/summary', 'toc_title': 'October 13, 2026 — KB5128928 Cumulative Update'}]})
        self.assertEqual(framework(client, TODAY)[33]['releaseDate'], '2026/10/13')
        self.assertIn('KB5127687', framework(client, TODAY)[33]['version'])

    def test_insecure_or_unapproved_redirect_is_rejected(self):
        for url in ['http://learn.microsoft.com/a', 'https://unofficial.example/a']:
            with self.assertRaises(SourceError):
                https_url(url)


class UpdateBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.previous = json.loads((ROOT/'versions.json').read_text())
        self.results = {item['no']: {k: item[k] for k in ('version', 'releaseDate')} for item in self.previous['items']}

    def test_only_three_requested_fields_change(self):
        self.results[1]['version'] = '12.0.99999.0'
        self.results[1]['releaseDate'] = '2026/11/09'
        current = prepare_update(self.previous, self.results, '2026-11-09T08:30:05+09:00')
        self.assertEqual(immutable(current), immutable(self.previous))
        self.assertEqual(current['items'][0]['sources'], self.previous['items'][0]['sources'])
        self.assertNotEqual(current['checkedAt'], self.previous['checkedAt'])

    def test_missing_one_product_prevents_a_partial_refresh(self):
        self.results.pop(33)
        with self.assertRaises(SourceError):
            prepare_update(self.previous, self.results, '2026-11-09T08:30:05+09:00')

    def test_source_or_product_name_updates_are_rejected(self):
        for key in ('sources', 'name'):
            changed = copy.deepcopy(self.results)
            changed[1][key] = 'not allowed'
            with self.assertRaises(SourceError):
                prepare_update(self.previous, changed, '2026-11-09T08:30:05+09:00')

    def test_failed_research_preserves_html_and_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'checkout'
            directory.mkdir()
            original = json.dumps(self.previous)
            (directory/'versions.json').write_text(original)
            (directory/'index.html').write_text('existing published page')
            report = Path(tmp)/'report.json'
            with patch.object(refresh, 'ROOT', directory), patch.object(refresh, 'refresh', return_value=(None, {'failures': ['network error']})), patch('sys.argv', ['refresh.py', '--report', str(report)]):
                with self.assertRaises(SystemExit):
                    refresh.main()
            self.assertEqual((directory/'versions.json').read_text(), original)
            self.assertEqual((directory/'index.html').read_text(), 'existing published page')
            self.assertTrue(report.exists())

    def test_cron_sunday_to_thursday_maps_to_jst_weekdays(self):
        workflow = (ROOT/'.github/workflows/refresh-versions.yml').read_text()
        self.assertIn("cron: '15 23 * * 0-4'", workflow)
        sunday = datetime(2026, 11, 8, 23, 15, tzinfo=timezone.utc)
        local = [(sunday+timedelta(days=i)).astimezone(ZoneInfo('Asia/Tokyo')) for i in range(5)]
        self.assertEqual([d.weekday() for d in local], [0, 1, 2, 3, 4])
        self.assertTrue(all((d.hour, d.minute) == (8, 15) for d in local))


class PublicationTests(unittest.TestCase):
    def test_success_of_previous_commit_does_not_verify_new_publication(self):
        self.assertFalse(check_build({'commit': 'old', 'status': 'built'}, 'new'))
        self.assertTrue(check_build({'commit': 'new', 'status': 'built'}, 'new'))
        with self.assertRaises(RuntimeError):
            check_build({'commit': 'new', 'status': 'errored'}, 'new')

    def test_bot_push_explicitly_requests_pages_build(self):
        class API:
            def __init__(self): self.posts = []; self.reads = 0
            def request(self, path, method='GET'):
                if method == 'POST': self.posts.append(path); return {}
                self.reads += 1
                return {'commit': 'old' if self.reads == 1 else 'new', 'status': 'built'}
        api = API()
        wait_for_build(api, 'new')
        self.assertEqual(api.posts, ['/pages/builds'])


if __name__ == '__main__':
    unittest.main()
