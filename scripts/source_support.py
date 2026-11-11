"""Read official sources without executing downloaded files or disabling TLS."""
import gzip
import hashlib
import json
import re
import ssl
import struct
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

OFFICIAL_HOSTS = {
    'aka.ms', 'learn.microsoft.com', 'support.microsoft.com', 'www.microsoft.com',
    'download.microsoft.com', 'download.visualstudio.microsoft.com',
    'docs.aws.amazon.com', 'docs.amazonaws.cn', 'dotnet.microsoft.com',
    'builds.dotnet.microsoft.com', 'github.com', 'raw.githubusercontent.com',
    's3.amazonaws.com',
    'www.ntt-tx.co.jp', 'www.hitachi.com', 'oip.manual.canon',
}


def response_limit(url):
    # The official SSM Windows bundle is larger than the usual document/installers.
    if url == 'https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/windows_amd64/AmazonSSMAgentSetup.exe':
        return 128 * 1024 * 1024
    return 40 * 1024 * 1024


class SourceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise SourceError(message)


def https_url(url):
    parts = urlsplit(url)
    require(parts.scheme == 'https' and parts.hostname in OFFICIAL_HOSTS
            and not parts.username and not parts.password, f'Unapproved official source: {parts.hostname}')
    if parts.hostname == 's3.amazonaws.com':
        require(parts.path.startswith('/ec2-downloads-windows/SSMAgent/'), 'Only the AWS-owned SSM distribution bucket is allowed')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    """Cache only within this run; retain provenance, never credentials or binaries."""
    def __init__(self):
        self.evidence = {}
        self._lock = threading.Lock()
        self._cache = {}

    def get(self, url):
        https_url(url)
        # One lock per URL permits independent official sources to load concurrently.
        with self._lock:
            entry = self._cache.setdefault(url, {'lock': threading.Lock()})
        with entry['lock']:
            if 'data' in entry:
                return entry['data']
            opener = urllib.request.build_opener(Redirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
            request = urllib.request.Request(url, headers={'User-Agent': 'software-versions/1.0 official-release-check', 'Accept-Encoding': 'identity'})
            for attempt in range(2):
                try:
                    with opener.open(request, timeout=35) as response:
                        https_url(response.url)
                        limit = response_limit(url)
                        payload = response.read(limit + 1)
                        require(len(payload) <= limit, 'Official response exceeds size limit')
                        result = dict(url=url, finalUrl=response.url, httpStatus=response.status,
                                      retrievedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                      sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload))
                        if payload[:2] == b'\x1f\x8b':
                            payload = gzip.decompress(payload)
                        with self._lock:
                            self.evidence[url] = result
                        entry['data'] = payload
                        return payload
                except urllib.error.HTTPError as error:
                    if attempt == 0 and error.code in (429, 502, 503, 504):
                        retry = error.headers.get('Retry-After', '5')
                        delay = int(retry) if retry.isdigit() else 5
                        if delay <= 60:
                            time.sleep(max(1, delay))
                            continue
                    raise SourceError(f'Official source HTTP {error.code}: {url}') from error
            raise SourceError('Official request failed')

    def doc(self, url):
        return Document(self.get(url).decode('utf-8-sig'))

    def json(self, url):
        return json.loads(self.get(url))


VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []
        self.parent = None

    def nodes(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.nodes()

    def text(self):
        if self.tag in ('script', 'style'):
            return ''
        return re.sub(r'\s+', ' ', ' '.join(c.text() if isinstance(c, Node) else c for c in self.children)).strip()

    def find_all(self, tag):
        return [n for n in self.nodes() if n.tag == tag]


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.stack = [self.root]
        self.feed(html)
        self.flat = list(self.root.nodes())

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        node.parent = self.stack[-1]
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, attrs)
        node.parent = self.stack[-1]
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def text(self):
        return self.root.text()

    def headings(self, pattern):
        for i, node in enumerate(self.flat):
            if node.tag not in ('h1', 'h2', 'h3', 'h4') or not re.search(pattern, node.text(), re.I):
                continue
            end = i + 1
            while end < len(self.flat):
                following = self.flat[end]
                if following.tag in ('h1', 'h2', 'h3', 'h4') and following.tag <= node.tag:
                    break
                end += 1
            nodes = self.flat[i:end]
            # Include complete blocks once, rather than repeating every descendant's text.
            parts = [n.text() for n in nodes if n.tag in ('h1', 'h2', 'h3', 'h4', 'p', 'li', 'td', 'th')]
            yield node.text(), ' '.join(parts), nodes

    def tables(self, nodes=None):
        for table in self.flat if nodes is None else nodes:
            if table.tag != 'table':
                continue
            rows = []
            for row in table.find_all('tr'):
                cells = [n.text() for n in row.children if isinstance(n, Node) and n.tag in ('td', 'th')]
                if cells:
                    rows.append(cells)
            if rows:
                yield rows


def version_key(version):
    require(bool(re.fullmatch(r'\d+(?:\.\d+){1,3}', version)), f'Invalid stable version: {version}')
    return tuple(map(int, version.split('.')))


DATE_PATTERN = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}'


def release_date(text):
    match = re.search(DATE_PATTERN, text, re.I)
    if match:
        value = datetime.strptime(re.sub(r',', '', match.group()), '%B %d %Y').date()
    else:
        match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', text)
        require(match is not None, f'No formal release date in: {text[:100]}')
        value = date(*map(int, match.groups()))
    return value


def published(value, today):
    require(value <= today, f'Future release date: {value}')
    return value.strftime('%Y/%m/%d')


def pe_version(payload):
    """Read VS_FIXEDFILEINFO from the VERSION resource; do not run the EXE."""
    def u16(offset): return struct.unpack_from('<H', payload, offset)[0]
    def u32(offset): return struct.unpack_from('<I', payload, offset)[0]
    require(payload[:2] == b'MZ', 'Expected a Microsoft PE installer')
    pe = u32(0x3c)
    require(payload[pe:pe+4] == b'PE\0\0', 'Invalid PE header')
    count, optional = u16(pe+6), pe+24
    magic = u16(optional)
    require(magic in (0x10b, 0x20b), 'Unsupported PE optional header')
    directory = optional + (96 if magic == 0x10b else 112)
    sections = optional + u16(pe+20)

    def offset(rva):
        for i in range(count):
            size, address, raw_size, raw = struct.unpack_from('<IIII', payload, sections+40*i+8)
            if address <= rva < address+max(size, raw_size):
                return raw+rva-address
        raise SourceError('PE resource outside sections')
    base = offset(u32(directory+16))

    def entries(relative):
        pos = base+relative
        return [struct.unpack_from('<II', payload, pos+16+i*8) for i in range(u16(pos+12)+u16(pos+14))]
    target = next(target for name, target in entries(0) if name == 16)
    target = entries(target & 0x7fffffff)[0][1]
    target = entries(target & 0x7fffffff)[0][1]
    require(not target & 0x80000000, 'Invalid version resource tree')
    pos = offset(u32(base+target))
    cursor = pos+6
    key = []
    while u16(cursor):
        key.append(chr(u16(cursor)))
        cursor += 2
    require(''.join(key) == 'VS_VERSION_INFO', 'Invalid version resource key')
    fields = struct.unpack_from('<13I', payload, (cursor+5) & ~3)
    require(fields[0] == 0xFEEF04BD, 'Invalid fixed file information')

    def ver(ms, ls): return '.'.join(str(x) for x in (ms >> 16, ms & 65535, ls >> 16, ls & 65535))
    file_version, product_version = ver(fields[2], fields[3]), ver(fields[4], fields[5])
    require(file_version == product_version, 'Installer file/product versions disagree')
    return file_version
