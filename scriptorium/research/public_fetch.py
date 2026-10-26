"""Bounded public-only fetching. DNS is checked and pinned at connection time."""
import ipaddress
import socket
import time
from urllib.parse import urlsplit, urljoin, urlunsplit, parse_qsl, urlencode
import httpx
from httpcore._backends.sync import SyncBackend
from .service import ResearchError


def normalized_url(url, canonical=False):
    p = urlsplit(url)
    if p.scheme not in {'http', 'https'} or not p.hostname or p.username or p.password:
        raise ResearchError('PUBLIC_URL_REQUIRED', 422)
    if p.port not in (None, 80, 443):
        raise ResearchError('PUBLIC_URL_PORT_NOT_ALLOWED', 422)
    host = p.hostname.encode('idna').decode().lower()
    try:
        if not ipaddress.ip_address(host).is_global or ipaddress.ip_address(host).is_multicast:raise ResearchError('PUBLIC_URL_PRIVATE_ADDRESS_BLOCKED',422)
    except ValueError:
        if host=='localhost' or host.endswith(('.localhost','.local')):raise ResearchError('PUBLIC_URL_PRIVATE_ADDRESS_BLOCKED',422)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in {'fbclid', 'gclid'}]
    return urlunsplit((p.scheme, host if ':' not in host else '[' + host + ']', p.path or '/', urlencode(query) if canonical else p.query, ''))


def public_addresses(host, port):
    addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast for a in addresses):
        raise ResearchError('PUBLIC_URL_PRIVATE_ADDRESS_BLOCKED', 422)
    return addresses


class PublicBackend(SyncBackend):
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        host = host.decode() if isinstance(host, bytes) else host
        address = public_addresses(host, port)[0]
        return super().connect_tcp(address, port, timeout, local_address, socket_options)


class PublicTransport(httpx.HTTPTransport):
    def __init__(self):
        super().__init__(trust_env=False)
        # httpcore keeps the original origin for certificate validation and SNI.
        self._pool._network_backend = PublicBackend()


def fetch(url, check=lambda: None, maximum=20 * 1024 * 1024):
    url = normalized_url(url)
    deadline=time.monotonic()+60
    def guarded():
        check()
        if time.monotonic()>deadline:raise ResearchError('SOURCE_FETCH_TIMEOUT',504)
    with httpx.Client(transport=PublicTransport(), trust_env=False, timeout=20, follow_redirects=False) as client:
        for _ in range(6):
            guarded()
            p = urlsplit(url); public_addresses(p.hostname, p.port or (443 if p.scheme == 'https' else 80))
            with client.stream('GET', url, headers={'User-Agent': 'Scriptorium/3.4 (research source collector)',
                                                  'Accept': 'text/html,text/plain,application/pdf'}) as response:
                if response.is_redirect:
                    url = normalized_url(urljoin(url, response.headers.get('location', '')))
                    continue
                if response.status_code in {401, 403, 402}:
                    raise ResearchError('SOURCE_ACCESS_RESTRICTED', 403)
                response.raise_for_status()
                mime = response.headers.get('content-type', '').split(';')[0].lower()
                if mime not in {'text/html', 'application/xhtml+xml', 'text/plain', 'text/markdown', 'application/pdf'}:
                    raise ResearchError('SOURCE_CONTENT_TYPE_UNSUPPORTED', 415)
                if int(response.headers.get('content-length', '0')) > maximum:
                    raise ResearchError('SOURCE_DOWNLOAD_LIMIT', 413)
                content = bytearray()
                for chunk in response.iter_bytes():
                    guarded(); content.extend(chunk)
                    if len(content) > maximum:
                        raise ResearchError('SOURCE_DOWNLOAD_LIMIT', 413)
                return bytes(content), mime, url
    raise ResearchError('SOURCE_REDIRECT_LIMIT', 422)


def html_document(raw):
    import re
    from lxml import html
    encoding=None
    match=re.search(br'charset=["\\\']?([a-zA-Z0-9_-]+)',raw[:8192])
    if match:encoding=match[1].decode('ascii')
    if not encoding:
        try:raw.decode('utf-8-sig');encoding='utf-8'
        except UnicodeDecodeError:
            try:raw.decode('gb18030');encoding='gb18030'
            except UnicodeDecodeError:encoding='windows-1252'
    try:return html.fromstring(raw,parser=html.HTMLParser(encoding=encoding))
    except LookupError:raise ResearchError('SOURCE_ENCODING_UNSUPPORTED',422) from None


def readable_html(raw):
    document = html_document(raw)
    import re
    paywall = any(re.search(r'"isAccessibleForFree"\s*:\s*(?:false|"false")', text, re.IGNORECASE) for text in document.xpath('//script[@type="application/ld+json"]/text()'))
    if paywall or (document.xpath('//input[@type="password"]') and not document.xpath('//article')):
        raise ResearchError('SOURCE_ACCESS_RESTRICTED',403)
    for node in document.xpath('//script|//style|//nav|//header|//footer|//noscript|//form'):
        node.drop_tree()
    title = ' '.join(document.xpath('//title/text()'))[:500]
    from trafilatura import extract
    from lxml import html
    serialized=html.tostring(document,encoding='unicode')
    text = extract(serialized if document.tag=='html' else '<html><body>'+serialized+'</body></html>',include_comments=False,include_tables=True,favor_precision=True) or ''
    if not text:
        article = document.xpath('//article|//main')
        scope = article[0] if article else document
        paragraphs = [' '.join(p.text_content().split()) for p in scope.xpath('.//p|.//h1|.//h2|.//h3|.//li|.//blockquote')]
        text = '\n\n'.join(p for p in paragraphs if p)
    import re
    text=re.sub(r'(?m)^(.{5,160})(?:\n\1){3,}',r'\1',text)
    landing=bool(document.xpath('//meta[@name="citation_title"]')) and not document.xpath('//article') and len(text)<1200
    catalog=bool(document.xpath('//table[contains(@class,"toc")]|//*[contains(@class,"table-of-contents")]')) and len(text)<1200
    if landing or catalog:
        raise ResearchError('SOURCE_BIBLIOGRAPHIC_PAGE' if landing else 'SOURCE_CONTENTS_ONLY',422)
    if len(text)<80:
        raise ResearchError('SOURCE_TEXT_INSUFFICIENT',422)
    return title, text


def html_metadata(raw):
    document=html_document(raw)
    def values(name):return [str(x).strip() for x in document.xpath('//meta[@name="'+name+'"]/@content') if str(x).strip()]
    return {k:v for k,v in {'author':'; '.join(values('citation_author')),'doi':next(iter(values('citation_doi')),''),
        'publication_date':next(iter(values('citation_publication_date')),''),'journal':next(iter(values('citation_journal_title')),'')}.items() if v}
