"""Conservative, product-specific readers for the 33 official-source checks."""
import re
from datetime import datetime
from urllib.parse import urljoin

from source_support import DATE_PATTERN, SourceError, pe_version, published, release_date, require, version_key

VC = 'https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist'
MSOLAP = 'https://learn.microsoft.com/en-us/analysis-services/client-libraries?view=asallproducts-allversions'
ODBC = 'https://learn.microsoft.com/en-us/sql/connect/odbc/windows/release-notes-odbc-sql-server-windows'
OLEDB = 'https://learn.microsoft.com/en-us/sql/connect/oledb/release-notes-for-oledb-driver-for-sql-server'
SSMS = 'https://learn.microsoft.com/en-us/ssms/release-notes-20'
VSTA = 'https://www.microsoft.com/ja-jp/download/details.aspx?id=58317'
EC2 = 'https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2launchv2-versions.html'
SSM_WINDOWS = 'https://docs.aws.amazon.com/systems-manager/latest/userguide/manually-install-ssm-agent-windows.html'
SSM_WINDOWS_INSTALLER = 'https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/windows_amd64/AmazonSSMAgentSetup.exe'
PV = 'https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/xen-drivers-overview.html'
CFN = 'https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/releasehistory-aws-cfn-bootstrap.html'
CFN_JA = 'https://docs.aws.amazon.com/ja_jp/AWSCloudFormation/latest/TemplateReference/releasehistory-aws-cfn-bootstrap.html'
CFN_CN = 'https://docs.amazonaws.cn/en_us/AWSCloudFormation/latest/TemplateReference/releasehistory-aws-cfn-bootstrap.html'
CSL = 'https://www.ntt-tx.co.jp/whatsnew/2022/221209.html'
SNMP = 'https://www.hitachi.com/products/it/software/security/info/vuls/hitachi-sec-2024-127/'
CLI_CHANGELOG = 'https://raw.githubusercontent.com/aws/aws-cli/v2/CHANGELOG.rst'
CLI_INSTALL = 'https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html'
NET_PAGE = 'https://dotnet.microsoft.com/en-us/download/dotnet/8.0'
NET_META = 'https://builds.dotnet.microsoft.com/dotnet/release-metadata/8.0/releases.json'
OPTIONS = 'https://learn.microsoft.com/en-us/aspnet/core/host-and-deploy/iis/hosting-bundle?view=aspnetcore-8.0'
CANON = 'https://oip.manual.canon/USRMA-3660-zz-DR-enUV/contents/dwu-inst-updt_uninst-uninst.html'
WINDOWS = 'https://support.microsoft.com/en-us/servicing/os/windows-server/2021/07/windows-server-2022-update-history'
OFFICE = 'https://learn.microsoft.com/en-us/officeupdates/update-history-office-2024'
EDGE = 'https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnote-stable-channel'
SQL = 'https://support.microsoft.com/en-us/servicing/sql/sql-server-2022/kb5023451-build-versions'
JDBC = 'https://learn.microsoft.com/en-us/sql/connect/jdbc/release-notes-for-the-jdbc-driver'
FRAMEWORK_BASE = 'https://support.microsoft.com/en-us/servicing/dotnetframework/microsoft-server/2022/'
FRAMEWORK = FRAMEWORK_BASE + '2021/09/history-of-cumulative-updates-for-net-framework-for-windows-server-2022'


def result(version, date='未確認'):
    return {'version': version, 'releaseDate': date}


def vc(client, today):
    doc = client.doc(VC)
    versions = {}
    for _, _, nodes in doc.headings(r'^Visual Studio 2013 \(VC\+\+ 12\.0\)'):
        for rows in doc.tables(nodes):
            for row in rows[1:]:
                if row[0].upper() in ('X86', 'X64'):
                    require(re.fullmatch(r'12\.0\.\d+\.\d+', row[1]), 'VC 2013 series mismatch')
                    versions[row[0].upper()] = row[1]
    require(set(versions) == {'X86', 'X64'}, 'VC 2013 architecture rows missing')
    found = {1: result(versions['X86']), 2: result(versions['X64'])}
    links = {n.attrs.get('href') for n in doc.flat if n.tag == 'a'}
    for no, arch in [(3, 'x86'), (4, 'x64')]:
        url = f'https://aka.ms/vc14/vc_redist.{arch}.exe'
        require(url in links, f'Latest v14 {arch} official link missing')
        value = pe_version(client.get(url))
        require(value.startswith('14.'), 'Unexpected v14 installer series')
        found[no] = result(value)
    return found


def msolap(client, today):
    doc = client.doc(MSOLAP)
    for rows in doc.tables():
        if not any('Download' in cell for cell in rows[0]):
            continue
        candidates = {row[0]: row[1] for row in rows[1:] if len(row) >= 2 and re.fullmatch(r'MSOLAP \((?:amd64|x86)\)', row[0])}
        if len(candidates) == 2:
            require(len(set(candidates.values())) == 1, 'MSOLAP architecture versions disagree')
            version = next(iter(candidates.values()))
            version_key(version)
            return {5: result('MSOLAP ' + version)}
    raise SourceError('MSOLAP download rows missing')


def numbered_notes(doc, major, today, detail=False):
    # Validate the latest series entry. Ancient entries use different layouts and
    # must neither override it nor cause a fallback to an older release.
    blocks = list(doc.headings(rf'^{major}\.\d+(?:\.\d+)*$'))
    require(blocks, f'No formal release in {major} series')
    title, text, _ = max(blocks, key=lambda b: version_key(b[0]))
    match = re.search(r'(?:Version number|Release number):\s*(\d+(?:\.\d+){1,3})', text, re.I)
    version = match.group(1) if match else title
    require(version.startswith(f'{major}.'), 'Release series mismatch')
    match = re.search(r'(?:Released|Release date):\s*(' + DATE_PATTERN + ')', text, re.I)
    require(match is not None, f'Formal release date missing: {title}')
    date = published(release_date(match.group(1)), today)
    value = version
    if detail:
        build = re.search(r'Build number:\s*(\d+(?:\.\d+){3})', text, re.I)
        require(build is not None and build.group(1).startswith(f'{major}.'), 'SSMS detailed build missing')
        value += f'（ビルド {build.group(1)}）'
    return result(value, date)


def odbc(client, today): return {6: numbered_notes(client.doc(ODBC), 17, today)}
def oledb(client, today): return {7: numbered_notes(client.doc(OLEDB), 18, today)}
def ssms(client, today): return {8: numbered_notes(client.doc(SSMS), 20, today, detail=True)}


def vsta(client, today):
    doc = client.doc(VSTA)
    require('VSTA 2019' in doc.text(), 'VSTA 2019 product page changed')
    links = {n.attrs.get('href', '') for n in doc.flat if n.tag == 'a'}
    links = [url for url in links if re.fullmatch(r'https://download\.microsoft\.com/.*/vsta_2019_setup_JPN\.exe', url)]
    require(len(links) == 1, 'Current VSTA 2019 Japanese installer link missing/ambiguous')
    version = pe_version(client.get(links[0]))
    require(version.startswith('16.'), 'VSTA 2019 detailed version mismatch')
    # Date Published on the web page is not proof of this build's release date.
    return {9: result(version + '（公式配布ファイルの詳細バージョン）')}


def aws_table(doc, today, major=None, cfn=False):
    candidates = []
    for rows in doc.tables():
        headers = ' '.join(rows[0]).lower()
        if not ('release date' in headers or 'リリース日' in headers):
            continue
        for row in rows[1:]:
            if len(row) < 3:
                continue
            pattern = r'2\.0-\d+' if cfn else r'\d+\.\d+\.\d+'
            match = re.match(pattern, row[0])
            if not match or re.search(r'preview|beta|alpha', row[0], re.I):
                continue
            version = match.group()
            if major and not version.startswith(f'{major}.'):
                continue
            date_cell = row[1] if cfn else row[-1]
            key = (int(version.split('-')[1]),) if cfn else version_key(version)
            candidates.append((key, version, date_cell))
    require(candidates, 'AWS release table missing')
    _, version, date_cell = max(candidates, key=lambda r: r[0])
    return result(version, published(release_date(date_cell), today))


def ec2(client, today): return {10: aws_table(client.doc(EC2), today, major=2)}


def pv(client, today):
    doc = client.doc(PV)
    require(any(len(r) >= 2 and r[0] == 'Windows Server 2022' and 'latest version' in r[1]
                for rows in doc.tables() for r in rows), 'PV Server 2022 support no longer confirmed')
    return {13: aws_table(doc, today)}


def cfn(client, today):
    names = ('英語', '中国向け英語', '日本語')
    values = [aws_table(client.doc(url), today, cfn=True) for url in (CFN, CFN_CN, CFN_JA)]
    return {14: cfn_result(values, names)}


def cfn_result(values, names=('英語', '中国向け英語', '日本語')):
    if len({(v['version'], v['releaseDate']) for v in values}) == 1:
        return values[0]
    if values[0] == values[1]:
        version = values[0]['version'] + f'（英語・中国向け英語。日本語は{values[2]["version"]}／{values[2]["releaseDate"]}。公式掲載差異あり）'
        return result(version, values[0]['releaseDate'])
    details = '／'.join(f'{name}：{v["version"]}・{v["releaseDate"]}' for name, v in zip(names, values))
    return result(f'最新版未確定（公式掲載差異：{details}）')


def github_release(client, repo, today):
    doc = client.doc(f'https://github.com/{repo}/releases')
    candidates = []
    for section in (n for n in doc.flat if n.tag == 'section' and n.attrs.get('id', '').startswith('release-')):
        titles = section.find_all('h2')
        if not titles or re.search(r'preview|pre-release|alpha|beta|release candidate', titles[0].text(), re.I):
            continue
        if any('Pre-release' in n.text() for n in section.nodes() if 'Label--warning' in n.attrs.get('class', '')):
            continue
        links = [n.attrs.get('href', '') for n in section.find_all('a')]
        tags = [url.split('/releases/tag/', 1)[1] for url in links if url.startswith(f'/{repo}/releases/tag/')]
        if not tags:
            continue
        version = tags[0].removeprefix('v')
        if not re.fullmatch(r'\d+(?:\.\d+){2,3}', version):
            continue
        times = section.find_all('relative-time')
        require(times, 'GitHub release publication time missing')
        date = datetime.fromisoformat(times[0].attrs['datetime'].replace('Z', '+00:00')).date()
        candidates.append((version_key(version), result(version, published(date, today))))
    require(candidates, f'No stable GitHub release found for {repo}')
    return max(candidates, key=lambda x: x[0])[1]


def ssm(client, today):
    doc = client.doc(SSM_WINDOWS)
    links = {node.attrs.get('href') for node in doc.root.find_all('a')}
    require(SSM_WINDOWS_INSTALLER in links, 'AWS official Windows x64 SSM installer link missing')
    # Read the actual distribution artifact, without executing or installing it.
    # A GitHub source release may precede the Windows installer distribution.
    version = pe_version(client.get(SSM_WINDOWS_INSTALLER))
    require(re.fullmatch(r'[1-9]\d*(?:\.\d+){3}', version), 'SSM Windows installer detailed version missing')
    # File timestamps and the GitHub publication date are not its formal release date.
    return {11: result(version + '（AWS公式Windows x64配布版）')}


def tera(client, today): return {17: github_release(client, 'TeraTermProject/teraterm', today)}


def cli(client, today):
    changelog = client.get(CLI_CHANGELOG).decode('utf-8')
    match = re.search(r'^([2]\.\d+\.\d+)\n=+\n', changelog, re.M)
    require(match is not None, 'AWS CLI v2 current changelog missing')
    version = match.group(1)
    doc = client.doc(f'https://github.com/aws/aws-cli/releases/tag/{version}')
    require(f'Tagging {version} release.' in doc.text(), 'AWS CLI official release tag mismatch')
    times = doc.root.find_all('relative-time')
    require(times, 'AWS CLI formal tag date missing')
    date = datetime.fromisoformat(times[0].attrs['datetime'].replace('Z', '+00:00')).date()
    install = client.doc(CLI_INSTALL)
    require('https://awscli.amazonaws.com/AWSCLIV2.msi' in install.text() and '64-bit' in install.text(), 'Windows 64-bit MSI offering missing')
    return {12: result(version + '（Windows用64ビットMSIの提供案内も確認）', published(date, today))}


def csl(client, today):
    require('CSLGuard' in client.doc(CSL).text(), 'CSLGuard official reference changed')
    return {15: result('最新版未確定（Agent単体の公式公開値・公開日を確認できず）')}


def snmp(client, today):
    require('JP1/Extensible SNMP Agent' in client.doc(SNMP).text(), 'SNMP candidate reference changed')
    # A similarly named JP1 product is not proof of the installed product's identity.
    return {16: result('最新版未確定（製造元・製品系列未特定）')}


def dotnet(client, today):
    require('.NET 8.0' in client.doc(NET_PAGE).text(), 'NET 8 official download page changed')
    meta = client.json(NET_META)
    latest = meta['latest-release']
    require(re.fullmatch(r'8\.0\.\d+', latest), 'Unexpected .NET 8 stable release')
    release = next(r for r in meta['releases'] if r['release-version'] == latest)
    date = published(datetime.strptime(release['release-date'], '%Y-%m-%d').date(), today)
    runtime, aspnet = release['runtime'], release['aspnetcore-runtime']
    for package in (runtime, aspnet):
        require(re.fullmatch(r'8\.0\.\d+', package['version']), 'Runtime is not NET 8 stable')
        for rid in ('win-x86', 'win-x64'):
            require(any(f['rid'] == rid and f['name'].endswith('.exe') for f in package['files']), f'NET installer missing: {rid}')
    require(any('hosting' in f['name'] and f['name'].endswith('.exe') for f in aspnet['files']), 'NET 8 Hosting Bundle installer missing')
    modules = aspnet['version-aspnetcoremodule']
    require(len(modules) == 1 and re.fullmatch(r'\d+(?:\.\d+){3}', modules[0]), 'ANCM detailed version ambiguous')
    return {18: result('Hosting Bundle ' + aspnet['version'], date),
            19: result(runtime['version'], date), 20: result(runtime['version'], date),
            21: result(aspnet['version'], date), 22: result(aspnet['version'], date),
            24: result(modules[0], date)}


def options(client, today):
    text = client.doc(OPTIONS).text()
    require(all(option in text for option in ('OPT_NO_ANCM', 'OPT_NO_RUNTIME', 'OPT_NO_SHAREDFX')), 'Hosting Bundle Options reference changed')
    return {23: result('最新版未確定（Options単体の公開バージョンを確認できず）')}


def canon(client, today):
    require('UNINSTAL.exe' in client.doc(CANON).text(), 'Canon uninstaller reference changed')
    return {25: result('最新版未確定（アンインストーラー単体の公式公開バージョンを確認できず）')}


def toc_nodes(items):
    for item in items:
        yield item
        yield from toc_nodes(item.get('children', []))


def windows(client, today):
    history = client.doc(WINDOWS)
    toc = next((n.attrs.get('content') for n in history.flat if n.tag == 'meta' and n.attrs.get('name') == 'toc_rel'), None)
    require(toc, 'Windows official update history TOC link missing')
    toc_url = urljoin(WINDOWS, toc)
    items = client.json(toc_url)['items']
    groups = [n for n in items if n.get('toc_title') == 'Windows Server 2022']
    require(len(groups) == 1, 'Server 2022 update group missing')
    candidates = []
    for item in toc_nodes(groups[0].get('children', [])):
        title = item.get('toc_title', '')
        if re.search(r'preview', title, re.I):
            continue
        kb = re.search(r'KB\d{7}', title)
        build = re.search(r'OS Build\s+(20348\.\d+)', title)
        if kb and build:
            date = release_date(title)
            if date <= today:
                candidates.append((date, int(build.group(1).split('.')[1]), item, kb.group(), build.group(1)))
    require(candidates, 'No released Server 2022 cumulative update')
    date, _, item, kb, build = max(candidates, key=lambda x: x[:2])
    article = client.doc(urljoin(toc_url, item['href']))
    require(any(kb in n.text() and build in n.text() for n in article.root.find_all('h1')), 'OS KB/build mismatch in official article')
    suffix = '、帯域外更新' if 'out-of-band' in item['toc_title'].lower() else ''
    return {26: result(f'{kb}（OSビルド {build}{suffix}）', published(date, today))}


def office(client, today):
    doc = client.doc(OFFICE)
    require('Office LTSC 2024' in doc.text(), 'Office LTSC 2024 history missing')
    candidates = []
    for rows in doc.tables():
        if not ('Release date' in rows[0] and 'Version number' in rows[0]):
            continue
        for row in rows[1:]:
            if len(row) < 2:
                continue
            match = re.fullmatch(r'Version (\d+) \(Build (\d+\.\d+)\)', row[1])
            if match:
                date = release_date(row[0])
                if date <= today:
                    candidates.append((date, version_key(match.group(2)), result(f'バージョン {match.group(1)}（ビルド {match.group(2)}）', published(date, today))))
    require(candidates, 'Office LTSC 2024 releases missing')
    return {27: max(candidates, key=lambda r: r[:2])[2]}


def edge(client, today):
    doc = client.doc(EDGE)
    candidates = []
    for title, _, _ in doc.headings(r'^Version \d+\.\d+\.\d+\.\d+:'):
        match = re.fullmatch(r'Version (\d+(?:\.\d+){3}):\s*(' + DATE_PATTERN + r')\s*\(Stable\).*', title, re.I)
        if match:
            date = release_date(match.group(2))
            if date <= today:
                candidates.append((version_key(match.group(1)), result(match.group(1) + '（Stable）', published(date, today))))
    require(candidates, 'Edge Stable release missing; Extended Stable/preview cannot substitute')
    return {28: max(candidates, key=lambda x: x[0])[1]}


def sql_records(doc, today):
    records = {}
    for rows in doc.tables():
        headers = rows[0]
        product_columns = [i for i, h in enumerate(headers) if h.lower() in ('sql server build version', 'sql server product version', 'product version')]
        if not product_columns or not any('release date' in h.lower() for h in headers):
            continue
        column = product_columns[0]
        for row in rows[1:]:
            name = row[0]
            if not re.fullmatch(r'(?:CU\d+(?: \+ GDR)?|GDR)(?: \(Latest\))?', name):
                continue
            name = name.replace(' (Latest)', '')
            require(len(row) > column, 'SQL build row incomplete')
            version = row[column]
            require(re.fullmatch(r'16\.0\.\d+\.\d+', version), 'SQL Server 2022 product build mismatch')
            kb = set(re.findall(r'KB\d{7}', ' '.join(row)))
            require(len(kb) == 1, 'SQL build KB ambiguous')
            date = published(release_date(row[-1]), today)
            key = (name, version)
            records[key] = (name, next(iter(kb)), version, date)
    require(records, 'SQL Server 2022 build tables missing')
    return list(records.values())


def select_sql(records):
    standalone = [r for r in records if re.fullmatch(r'CU\d+', r[0])]
    require(standalone, 'SQL Server 2022 standalone CU missing')
    cu = max(standalone, key=lambda r: int(r[0][2:]))
    cu_gdr = [r for r in records if r[0] == cu[0] + ' + GDR']
    gdr = [r for r in records if r[0] == 'GDR']
    require(gdr, 'SQL Server 2022 GDR branch missing')
    return cu, max(cu_gdr, key=lambda r: version_key(r[2])) if cu_gdr else None, max(gdr, key=lambda r: version_key(r[2]))


def sql(client, today):
    doc = client.doc(SQL)
    require('SQL Server 2022' in doc.text(), 'SQL build list product mismatch')
    cu, cu_gdr, gdr = select_sql(sql_records(doc, today))
    output = {}
    for no, record in [(29, cu), (30, cu_gdr), (31, gdr)]:
        if record is None:
            output[no] = result(f'該当更新なし（最新{cu[0]}系統のCU＋GDRは公式一覧に掲載なし）')
            continue
        name, kb, version, date = record
        article = client.doc('https://support.microsoft.com/en-us/help/' + kb[2:])
        require(any(kb in n.text() for n in article.root.find_all('h1')), f'SQL {kb} official article mismatch')
        text = article.text()
        release = re.search(r'Release date:\s*(' + DATE_PATTERN + ')', text, re.I)
        require(release and published(release_date(release.group(1)), today) == date, 'SQL index/article release date mismatch')
        require(re.search(r'Version:\s*' + re.escape(version) + r'\b', text, re.I), 'SQL index/article product build mismatch')
        label = name.replace(' + ', '＋')
        output[no] = result(f'{label}／{kb}／ビルド {version}', date)
    return output


def jdbc(client, today):
    value = github_release(client, 'microsoft/mssql-jdbc', today)
    doc = client.doc(JDBC)
    versions = []
    for title, text, _ in doc.headings(r'^\d+\.\d+$'):
        match = re.search(r'Release number:\s*(\d+\.\d+\.\d+)', text)
        date = re.search(r'Released:\s*(' + DATE_PATTERN + ')', text, re.I)
        if match and date:
            versions.append((version_key(match.group(1)), match.group(1), published(release_date(date.group(1)), today)))
    require(versions, 'JDBC official release notes missing')
    _, notes_version, notes_date = max(versions, key=lambda r: r[0])
    require(version_key(value['version']) >= version_key(notes_version), 'JDBC release-note/GitHub precedence needs manual review')
    suffix = f'（正式版。公式リリースノートは{notes_version}／{notes_date}の掲載）' if notes_version != value['version'] else '（正式版）'
    return {32: result(value['version'] + suffix, value['releaseDate'])}


def framework(client, today):
    require('Framework' in client.doc(FRAMEWORK).text(), 'Framework history missing')
    toc = client.json(FRAMEWORK_BASE + 'toc.json')
    candidates = []
    for node in toc_nodes(toc['items']):
        if not node.get('href') or 'KB' not in node.get('toc_title', ''):
            continue
        date = release_date(node['toc_title'])
        if date <= today:
            candidates.append((date, node['href']))
    require(candidates, 'Framework official history has no dated updates')
    _, href = max(candidates, key=lambda r: r[0])
    summary_url = urljoin(FRAMEWORK_BASE, href)
    summary = client.doc(summary_url)
    links = {}
    main = next((n for n in summary.flat if n.tag == 'main'), None)
    require(main is not None, 'Framework article body missing')
    for anchor in main.find_all('a'):
        context = anchor
        while context.parent is not None and context.tag not in ('p', 'li', 'td'):
            context = context.parent
        title = context.text()
        if '4.8.1' in title or 'Windows Server 2022' not in title:
            continue
        if not re.search(r'3\.5\s*(?:and|,)\s*4\.8\b', title):
            continue
        kb = re.search(r'\b(?:KB)?(\d{7})\b', title)
        if kb:
            links[kb.group(1)] = urljoin(summary_url, anchor.attrs['href'])
    require(len(links) == 1, 'Framework 3.5/4.8 specific KB missing; 4.8.1/aggregate KB cannot substitute')
    number, url = next(iter(links.items()))
    article = client.doc(url)
    title = ' '.join(n.text() for n in article.root.find_all('h1'))
    require(number in title and '4.8.1' not in title and 'Windows Server 2022' in title, 'Framework individual KB product mismatch')
    match = re.search(r'Release Date:\s*(' + DATE_PATTERN + ')', article.text(), re.I)
    require(match, 'Framework KB formal release date missing')
    return {33: result(f'KB{number}（Windows Server 2022向け.NET Framework 3.5／4.8）', published(release_date(match.group(1)), today))}


COLLECTORS = [vc, msolap, odbc, oledb, ssms, vsta, ec2, ssm, cli, pv, cfn,
              csl, snmp, tera, dotnet, options, canon, windows, office, edge, sql, jdbc, framework]
