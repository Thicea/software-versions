"""Request an existing branch-based Pages build, then verify the actual HTML."""
import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('GitHub API redirect refused to protect authentication')


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid repository identity')
        self.base = f'https://api.github.com/repos/{repository}'
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path, method='GET'):
        if not path.startswith('/pages'):
            raise ValueError('Only this repository Pages API is allowed')
        request = urllib.request.Request(self.base + path, data=b'{}' if method == 'POST' else None, method=method,
                                         headers={'Authorization': f'Bearer {self.token}',
                                                  'Accept': 'application/vnd.github+json',
                                                  'X-GitHub-Api-Version': '2022-11-28',
                                                  'Content-Type': 'application/json',
                                                  'User-Agent': 'software-versions-publisher'})
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'GitHub Pages API {method} {path}: HTTP {error.code}') from None


def check_build(build, commit):
    if build.get('commit') != commit:
        return False
    if build.get('status') == 'errored':
        raise RuntimeError('The Pages build failed; inspect Pages build logs')
    return build.get('status') == 'built'


def wait_for_build(github, commit, timeout=600):
    latest = github.request('/pages/builds/latest')
    if latest.get('commit') != commit or latest.get('status') == 'errored':
        # GITHUB_TOKEN pushes don't automatically trigger the existing Pages build.
        # This explicit API request builds the repository's configured main branch.
        github.request('/pages/builds', method='POST')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        latest = github.request('/pages/builds/latest')
        if check_build(latest, commit):
            return
        print(f'Pages: {latest.get("status")} ({str(latest.get("commit", ""))[:7]})', flush=True)
        time.sleep(15)
    raise RuntimeError('Timed out waiting for the Pages build of the exact pushed commit')


def verify_html(url, expected, timeout=180):
    if not url.startswith('https://'):
        raise ValueError('Public Pages URL must use HTTPS')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'software-versions-publication-check'})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                actual = response.read(2 * 1024 * 1024)
                if actual == expected:
                    print('Public HTML verified: SHA256 ' + hashlib.sha256(actual).hexdigest(), flush=True)
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(10)
    raise RuntimeError('Pages build completed, but the expected public HTML was not observed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
        raise ValueError('Expected a full commit SHA')
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        raise RuntimeError('The workflow-provided GITHUB_TOKEN is required for Pages build requests')
    github = GitHub(os.environ['GITHUB_REPOSITORY'], token)
    settings = github.request('/pages')
    source = settings.get('source', {})
    if settings.get('build_type') != 'legacy' or source.get('branch') != 'main' or source.get('path') != '/':
        raise RuntimeError('Expected existing Pages source main:/; settings were not changed automatically')
    wait_for_build(github, args.commit)
    expected = (Path(__file__).resolve().parents[1] / 'index.html').read_bytes()
    verify_html(settings['html_url'], expected)
    print('Published commit ' + args.commit)


if __name__ == '__main__':
    main()
