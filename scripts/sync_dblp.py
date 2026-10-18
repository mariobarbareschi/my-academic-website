#!/usr/bin/env python3
"""Update the local bibliography from DBLP with safe XML -> JSON fallback.

No third-party dependencies. The current JSON file is never replaced unless a
credible complete bibliography is downloaded and parsed successfully.
"""
import argparse
from datetime import datetime, timezone
from html import unescape, entities
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

PID = '134/1019'
XML_URL = f'https://dblp.org/pid/{PID}.xml'
API_URL = 'https://dblp.org/search/publ/api?' + urlencode({
    'q': 'author:Mario_Barbareschi:', 'h': 1000, 'format': 'json', 'c': 0
})
DEFAULT_OUT = Path(__file__).resolve().parents[1] / 'site/data/publications.json'
USER_AGENT = 'Mozilla/5.0 (compatible; AcademicWebsiteBibliography/1.1; +https://dblp.org/pid/134/1019)'


def flat(element):
    if element is None:
        return ''
    return ' '.join(unescape(''.join(element.itertext())).split()).strip()


def first(node, *names):
    for name in names:
        child = node.find(name)
        if child is not None and flat(child):
            return flat(child)
    return ''


def url_or_none(value):
    return value.strip() if isinstance(value, str) and value.strip().startswith('https://') else None


def decode_named_entities(xml_data):
    """Replace DBLP DTD entities that Python's ElementTree cannot resolve."""
    match = re.search(br'<\?xml[^>]*encoding=["\']([^"\']+)', xml_data[:200], flags=re.I)
    charset = match.group(1).decode('ascii') if match else 'utf-8-sig'
    xml_text = xml_data.decode(charset)

    def subst(m):
        name = m.group(1)
        if name in ('amp', 'lt', 'gt', 'quot', 'apos'):
            return m.group(0)
        codepoint = entities.name2codepoint.get(name)
        return '&#' + str(codepoint) + ';' if codepoint else m.group(0)

    return re.sub(r'&([A-Za-z][A-Za-z0-9]+);', subst, xml_text)


def parse_person_xml(xml_data):
    data = xml_data.lstrip(b'\xef\xbb\xbf \t\r\n')
    if not data.startswith(b'<'):
        raise ValueError('DBLP XML response is not XML; first bytes: ' + repr(data[:100]))
    root = ET.fromstring(decode_named_entities(xml_data))
    if root.tag.split('}')[-1] != 'dblpperson':
        raise ValueError('Expected DBLP <dblpperson>, received <' + root.tag + '>')
    records = [r[0] for r in root.findall('.//r') if len(r)]
    if not records:
        records = [node for node in root if node.tag in (
            'article', 'inproceedings', 'proceedings', 'incollection',
            'book', 'phdthesis', 'mastersthesis', 'www')]
    publications = []
    seen = set()
    for record in records:
        kind = record.tag.split('}')[-1]
        key = record.get('key', '')
        if not key or key in seen:
            continue
        title = first(record, 'title')
        year_str = first(record, 'year')
        if not title or not year_str.isdigit():
            continue
        year = int(year_str)
        if year < 1950 or year > datetime.now(timezone.utc).year + 3:
            continue
        authors = [flat(x) for x in record.findall('author')]
        if not authors:
            authors = [flat(x) for x in record.findall('editor')]
        typ = ('Journal' if kind == 'article' else
               'Conference' if kind in ('inproceedings', 'proceedings') else 'Other')
        venue = first(record, 'journal', 'booktitle', 'school', 'publisher', 'series')
        volume = first(record, 'volume')
        number = first(record, 'number')
        pages = first(record, 'pages')
        venue = ', '.join(v for v in (
            venue, 'vol. ' + volume if volume else '',
            'no. ' + number if number else '',
            'pp. ' + pages if pages else '') if v)
        ee = [flat(e) for e in record.findall('ee')]
        doi = next((v for v in ee if v.startswith('https://doi.org/')), None)
        if not doi:
            doi_text = first(record, 'doi')
            if doi_text:
                doi = 'https://doi.org/' + doi_text.removeprefix('https://doi.org/')
        pdf = next((v for v in ee if v.lower().split('?')[0].endswith('.pdf')), None)
        publications.append({
            'key': key, 'title': title, 'authors': authors, 'year': year,
            'type': typ, 'venue': venue, 'dblp_url': 'https://dblp.org/rec/' + key,
            'doi_url': url_or_none(doi), 'pdf_url': url_or_none(pdf),
        })
        seen.add(key)
    return sorted(publications, key=lambda p: (-p['year'], p['key']))


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _plain(value):
    if isinstance(value, dict):
        value = value.get('text', '')
    value = re.sub(r'<[^>]+>', '', str(value or ''))
    return ' '.join(unescape(value).split())


def parse_search_json(json_data):
    """Parse the documented DBLP publication-search API response.

    Verify Mario Barbareschi is named among authors to prevent publishing
    unrelated search hits if the search syntax changes.
    """
    doc = json.loads(json_data)
    if not isinstance(doc, dict) or 'result' not in doc:
        raise ValueError('Not a DBLP publication-search JSON response')
    hits_info = doc['result'].get('hits', {})
    hits = _as_list(hits_info.get('hit', []))
    result = []
    seen = set()
    for hit in hits:
        info = hit.get('info', {}) if isinstance(hit, dict) else {}
        if not isinstance(info, dict):
            continue
        key = info.get('key', '')
        if not key:
            link = info.get('url', '')
            if isinstance(link, str) and '/rec/' in link:
                key = link.split('/rec/', 1)[1].split('?', 1)[0].rstrip('/')
        if not isinstance(key, str) or not key or key in seen:
            continue
        title = _plain(info.get('title'))
        yr = str(info.get('year', ''))
        if not title or not yr.isdigit():
            continue
        year = int(yr)
        if not (1950 <= year <= datetime.now(timezone.utc).year + 3):
            continue
        author_block = info.get('authors', {})
        authors_data = author_block.get('author') if isinstance(author_block, dict) else author_block
        authors = [_plain(a) for a in _as_list(authors_data)]
        authors = [a for a in authors if a]
        if not any(a == 'Mario Barbareschi' or a.startswith('Mario Barbareschi ') for a in authors):
            continue
        category = str(info.get('type', '')).lower()
        key_prefix = key.split('/')[0]
        typ = ('Journal' if 'journal' in category or key_prefix == 'journals' else
               'Conference' if 'conference' in category or 'workshop' in category or key_prefix == 'conf' else 'Other')
        venue = _plain(info.get('venue', ''))
        if not venue:
            venue = _plain(info.get('journal') or info.get('booktitle'))
        volume = _plain(info.get('volume', ''))
        pages = _plain(info.get('pages', ''))
        venue = ', '.join(v for v in (
            venue, 'vol. ' + volume if volume else '', 'pp. ' + pages if pages else '') if v)
        links = [str(v) for v in _as_list(info.get('ee')) if isinstance(v, str)]
        doi = next((v for v in links if v.startswith('https://doi.org/')), None)
        doi_field = info.get('doi')
        if not doi and isinstance(doi_field, str) and doi_field:
            doi = 'https://doi.org/' + doi_field.removeprefix('https://doi.org/')
        pdf = next((v for v in links if v.lower().split('?')[0].endswith('.pdf')), None)
        result.append({
            'key': key, 'title': title, 'authors': authors, 'year': year,
            'type': typ, 'venue': venue, 'dblp_url': 'https://dblp.org/rec/' + key,
            'doi_url': url_or_none(doi), 'pdf_url': url_or_none(pdf),
        })
        seen.add(key)
    return sorted(result, key=lambda p: (-p['year'], p['key']))


def download(url, *, retries=2, timeout=30):
    """Fetch a DBLP response and surface useful information on bad responses."""
    last_error = None
    for attempt in range(retries):
        try:
            request = Request(url, headers={
                'User-Agent': USER_AGENT,
                'Accept': 'application/xml,application/json,text/xml;q=0.9,*/*;q=0.5',
            })
            with urlopen(request, timeout=timeout) as response:
                data = response.read()
                mime = response.headers.get('Content-Type', 'unknown')
            if not data:
                raise ValueError(f'Empty response from {url} (Content-Type: {mime})')
            if data.lstrip().lower().startswith((b'<!doctype html', b'<html')):
                raise ValueError(f'HTML instead of DBLP data from {url} (Content-Type: {mime})')
            return data
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f'{url}: {last_error}')


def get_bibliography(min_records):
    errors = []
    sources = (
        ('DBLP person XML', XML_URL, parse_person_xml),
        ('DBLP search JSON', API_URL, parse_search_json),
    )
    for source, url, parser in sources:
        try:
            papers = parser(download(url))
            if len(papers) < min_records:
                raise ValueError(f'{len(papers)} valid records (minimum {min_records})')
            print(f'Source: {source}; parsed {len(papers)} records.')
            return papers
        except (RuntimeError, ValueError, ET.ParseError, UnicodeError) as exc:
            errors.append(f'{source}: {exc}')
            print(f'Warning: {source} unavailable or invalid: {exc}', file=sys.stderr)
    raise RuntimeError('Both DBLP sources failed. ' + '; '.join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Local XML or JSON export for offline testing')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--min-records', type=int, default=20,
                        help='Minimum number of valid publications before replacing existing data')
    args = parser.parse_args()
    try:
        if args.input:
            payload = args.input.read_bytes()
            papers = (parse_search_json(payload) if payload.lstrip().startswith(b'{') else
                      parse_person_xml(payload))
        else:
            papers = get_bibliography(args.min_records)
        if len(papers) < args.min_records:
            raise ValueError(f'Only {len(papers)} publications parsed (minimum {args.min_records})')
        if args.output.exists():
            try:
                old = json.loads(args.output.read_text(encoding='utf-8'))
                if not old.get('bootstrap_only', True) and old.get('publications') == papers:
                    print(f'DBLP checked: {len(papers)} publications; unchanged.')
                    return 0
            except (ValueError, OSError, TypeError, AttributeError):
                pass
        dest = args.output
        dest.parent.mkdir(parents=True, exist_ok=True)
        output = {
            'source': 'dblp', 'author_pid': PID,
            'last_synced_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'bootstrap_only': False, 'publications': papers,
        }
        temporary = dest.with_name(dest.name + '.tmp')
        temporary.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        temporary.replace(dest)
        print(f'Synchronized {len(papers)} DBLP records into {dest}')
        return 0
    except Exception as exc:
        print('DBLP synchronization aborted; existing bibliography preserved: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
