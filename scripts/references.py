"""Choose verified public reference pages, preferring matching Japanese articles."""
import re
from urllib.error import URLError

from source_support import SourceError, release_date


def source(url, label):
    return {'label': label, 'url': url}


def article_reference(client, url, label, kb, build=None, date=None):
    # Use the resolved article URL, rather than a version-specific URL from a past run.
    canonical = getattr(client, 'evidence', {}).get(url, {}).get('finalUrl', url)
    fallback = source(canonical, label)
    if not canonical.startswith('https://support.microsoft.com/en-us/'):
        return fallback
    japanese = canonical.replace('/en-us/', '/ja-jp/', 1)
    try:
        doc = client.doc(japanese)
    except (SourceError, URLError, TimeoutError):
        return fallback
    headings = ' '.join(n.text() for n in doc.root.find_all('h1'))
    language = next((n.attrs.get('lang', '').lower() for n in doc.flat if n.tag == 'html'), '')
    text = doc.text()
    if not language.startswith('ja') or kb not in headings or (build and build not in text):
        return fallback
    if date:
        dates = re.findall(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日', text, re.I)
        if date not in {release_date(value).strftime('%Y/%m/%d') for value in dates}:
            return fallback
    resolved = getattr(client, 'evidence', {}).get(japanese, {}).get('finalUrl', japanese)
    if '/ja-jp/' not in resolved:
        return fallback
    return source(resolved, label)


def validate_reference_versions(data):
    """Reject old release tags/KB articles accidentally retained after a version update."""
    for item in data['items']:
        if item['no'] == 33:
            kb = re.search(r'KB(\d{7})', item['version'])
            if kb and (len(item['sources']) != 1 or kb.group(1) not in item['sources'][0]['url']):
                raise ValueError('No.33: 3.5／4.8専用KB記事のみを掲載してください')
        for ref in item['sources']:
            tag = re.search(r'/releases/tag/v?(\d+(?:\.\d+){2,3})(?:$|[?#])', ref['url'])
            if tag:
                version = re.search(r'\d+(?:\.\d+){2,3}', item['version'])
                if not version or version.group() != tag.group(1):
                    raise ValueError(f'No.{item["no"]}: 掲載バージョンとリリースURLが不一致です')
            if item['no'] in (26, 29, 30, 31, 33):
                article = re.search(r'(?:kb|/help/|[-/])(\d{7})(?:[-/]|$|[?#])', ref['url'], re.I)
                if article and article.group(1) != '5023451':  # SQL build-history index, not an individual update.
                    if 'KB' + article.group(1) not in item['version']:
                        raise ValueError(f'No.{item["no"]}: 掲載KBと記事URLが不一致です')
