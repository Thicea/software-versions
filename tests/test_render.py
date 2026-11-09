import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_update_scope
import render
from refresh import prepare_update
from source_support import Document, SourceError
from validate import validate

ROOT = Path(__file__).resolve().parents[1]


class ProductNameTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'versions.json').read_text())

    def test_json_only_rename_updates_page_and_product_list_without_research(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'templates').mkdir()
            (directory / 'templates/index.html').write_text((ROOT / 'templates/index.html').read_text())
            (directory / 'products.json').write_text(render.render_products(self.data))
            self.data['items'][6]['name'] = 'Microsoft OLE DB Driver <18> & SQL Server'
            original = json.dumps(self.data, ensure_ascii=False, indent=2) + '\n'
            (directory / 'versions.json').write_text(original)
            with patch.object(render, 'ROOT', directory):
                render.main()
            html = (directory / 'index.html').read_text()
            rows = [row for row in Document(html).root.find_all('tr') if row.children and row.children[0].tag == 'td' and len(row.children) == 5]
            self.assertEqual([row.children[1].text() for row in rows], [item['name'] for item in self.data['items']])
            products = json.loads((directory / 'products.json').read_text())
            self.assertEqual(products, [{'no': item['no'], 'name': item['name']} for item in self.data['items']])
            self.assertIn('&lt;18&gt; &amp; SQL Server', html)
            self.assertEqual((directory / 'versions.json').read_text(), original)
            self.assertIn(self.data['checkedAt'], html)

    def test_next_research_run_preserves_custom_display_name(self):
        self.data['items'][7]['name'] = 'SQL Server Management Studio'
        results = {item['no']: {key: item[key] for key in ('version', 'releaseDate')} for item in self.data['items']}
        updated = prepare_update(self.data, results, '2026-11-10T08:30:00+09:00')
        self.assertEqual(updated['items'][7]['name'], self.data['items'][7]['name'])

    def test_empty_display_names_and_changed_product_order_are_rejected(self):
        for name in ('', '  ', None):
            data = copy.deepcopy(self.data)
            data['items'][0]['name'] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate(data)
        self.data['items'][0], self.data['items'][1] = self.data['items'][1], self.data['items'][0]
        with self.assertRaises(ValueError):
            validate(self.data)


class GeneratedUpdateBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        (self.directory / 'templates').mkdir()
        (self.directory / 'templates/index.html').write_text((ROOT / 'templates/index.html').read_text())
        self.data = json.loads((ROOT / 'versions.json').read_text())
        (self.directory / 'versions.json').write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + '\n')
        (self.directory / 'products.json').write_text('[]\n')
        (self.directory / 'index.html').write_text('previous page\n')
        for args in (['init', '--quiet'], ['add', '.'],
                     ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--quiet', '-m', 'Saved versions.json']):
            subprocess.run(['git', *args], cwd=self.directory, check=True, capture_output=True)
        with patch.object(render, 'ROOT', self.directory):
            render.main()

    def test_render_only_accepts_synchronized_generated_files(self):
        with patch.object(check_update_scope, 'ROOT', self.directory), patch.object(render, 'ROOT', self.directory):
            check_update_scope.check(generated_only=True)

    def test_render_only_rejects_a_changed_research_timestamp(self):
        self.data['checkedAt'] = '2026-11-10T08:30:00+09:00'
        (self.directory / 'versions.json').write_text(json.dumps(self.data))
        with patch.object(check_update_scope, 'ROOT', self.directory), patch.object(render, 'ROOT', self.directory):
            with self.assertRaises(SourceError):
                check_update_scope.check(generated_only=True)

    def test_render_only_rejects_product_list_not_matching_versions_json(self):
        (self.directory / 'products.json').write_text('[]\n')
        with patch.object(check_update_scope, 'ROOT', self.directory), patch.object(render, 'ROOT', self.directory):
            with self.assertRaises(SourceError):
                check_update_scope.check(generated_only=True)


if __name__ == '__main__':
    unittest.main()
