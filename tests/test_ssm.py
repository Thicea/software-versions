import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_sources import SSM_WINDOWS, SSM_WINDOWS_INSTALLER, ssm
from source_support import Document, SourceError, https_url, response_limit


class AWSDistribution:
    def __init__(self, links=None):
        self.links = [SSM_WINDOWS_INSTALLER] if links is None else links
        self.requests = []

    def doc(self, url):
        self.requests.append(url)
        if url != SSM_WINDOWS:
            raise AssertionError('Unexpected reference source: ' + url)
        return Document(''.join(f'<a href="{link}">Windows installer</a>' for link in self.links))

    def get(self, url):
        self.requests.append(url)
        if url != SSM_WINDOWS_INSTALLER:
            raise AssertionError('Unexpected distribution source: ' + url)
        return b'installer fixture'


class SSMDistributionTests(unittest.TestCase):
    def test_actual_windows_distribution_is_used_without_github_or_inferred_date(self):
        client = AWSDistribution()
        with patch('research_sources.pe_version', return_value='3.3.5708.0') as read_version:
            value = ssm(client, date(2026, 11, 11))[11]
        self.assertEqual(value['version'], '3.3.5708.0（AWS公式Windows x64配布版）')
        self.assertEqual(value['releaseDate'], '未確認')
        self.assertEqual(client.requests, [SSM_WINDOWS, SSM_WINDOWS_INSTALLER])
        read_version.assert_called_once_with(b'installer fixture')

    def test_missing_x64_link_cannot_fall_back_to_x86_or_github(self):
        client = AWSDistribution([SSM_WINDOWS_INSTALLER.replace('windows_amd64', 'windows_386')])
        with self.assertRaises(SourceError):
            ssm(client, date(2026, 11, 11))
        self.assertEqual(client.requests, [SSM_WINDOWS])

    def test_generic_or_invalid_installer_version_is_rejected(self):
        for value in ['0.0.0.0', '3.3', 'unknown']:
            with self.subTest(value=value), patch('research_sources.pe_version', return_value=value):
                with self.assertRaises(SourceError):
                    ssm(AWSDistribution(), date(2026, 11, 11))

    def test_s3_access_is_limited_to_the_official_ssm_bucket(self):
        self.assertEqual(https_url(SSM_WINDOWS_INSTALLER), SSM_WINDOWS_INSTALLER)
        with self.assertRaises(SourceError):
            https_url('https://s3.amazonaws.com/unrelated-bucket/setup.exe')

    def test_large_file_allowance_is_only_for_the_official_ssm_x64_installer(self):
        self.assertEqual(response_limit(SSM_WINDOWS_INSTALLER), 128 * 1024 * 1024)
        self.assertEqual(response_limit(SSM_WINDOWS), 40 * 1024 * 1024)
        self.assertEqual(response_limit(SSM_WINDOWS_INSTALLER.replace('windows_amd64', 'windows_386')), 40 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
