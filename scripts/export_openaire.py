#!/usr/bin/env python3
"""One-off OpenAIRE coverage audit for Mario Barbareschi.

Queries OpenAIRE Graph API v4 by ORCID and by exact author name, writes
CSV/JSON/Markdown to an artifacts folder, and NEVER modifies site files.

Run: python3 scripts/export_openaire.py --output openaire-export
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'https://api.openaire.eu/graph/v4/research-products'
ORCID = '0000-0002-1417-6328'
AUTHOR = 'Mario Barbareschi'
CONTACT = 'mario.barbareschi@unina.it'
PAGE_SIZE = 100
MAX_PAGES = 30


def clean(value):
    if not isinstance(value, str):
        return ''
    return ' '.join(value.split())


def fold(value):
    value = unicodedata.normalize('NFKD', clean(value))
    return ''.join(ch for ch in value if not unicodedata.combining(ch)).casefold()


def author_match(author):
    """Return exact, initial-only or none; flag uncertain initial-only entries."""
    if not isinstance(author, dict):
        return 'none'
    candidates = [author.get('fullName'), author.get('fullname')]
    given, last = clean(author.get('name')), clean(author.get('surname'))
    if given and last:
        candidates.append(f'{given} {last}')
        candidates.append(f'{last} {given}')
    for item in candidates:
        value = fold(item)
        if not value:
            continue
        if re.search(r'\bbarbareschi\b', value) and re.search(r'\bmario\b', value):
            return 'exact'
    for item in candidates:
        value = fold(item)
        if re.search(r'\bbarbareschi\b', value) and re.search(r'\bm\.?\b', value):
            return 'initial-only'
    return 'none'


def linked_orcid(author):
    if not isinstance(author, dict):
        return ''
    pid = author.get('pid')
    if isinstance(pid, dict):
        idobj = pid.get('id', {})
        if isinstance(idobj, dict) and idobj.get('scheme', '').lower().startswith('orcid'):
            return clean(idobj.get('value'))
    for name in ('orcid', 'orcidId', 'orcid_id'):
        value = author.get(name)
        if isinstance(value, str):
            return value.removeprefix('https://orcid.org/')
    return ''


def names_authors(record):
    authors = record.get('authors') or []
    if isinstance(authors, dict):
        authors = [authors]
    return [a for a in authors if isinstance(a, dict)]


def get_doi(record):
    vals = []
    for value in record.get('pids') or []:
        if isinstance(value, dict):
            if fold(value.get('scheme', '')) == 'doi':
                vals.append(value.get('value'))
            p = value.get('pid')
            if isinstance(p, dict) and fold(p.get('scheme', '')) == 'doi':
                vals.append(p.get('value'))
    for instance in record.get('instances') or []:
        if not isinstance(instance, dict):
            continue
        for ident in instance.get('alternateIdentifiers') or []:
            if isinstance(ident, dict) and fold(ident.get('scheme', '')) == 'doi':
                vals.append(ident.get('value'))
    for val in vals:
        if isinstance(val, str) and val.strip():
            return re.sub(r'^https?://(?:dx\.)?doi\.org/', '', val.strip(), flags=re.I).lower()
    return ''


def record_key(record):
    doi = get_doi(record)
    if doi:
        return 'doi:' + doi
    ident = record.get('id')
    if ident:
        return 'openaire:' + str(ident)
    return 'title:' + fold(record.get('mainTitle', '')) + ':' + str(record.get('publicationDate', '')[:4])


def request_page(filter_value, page, timeout=45):
    params = {'filter': filter_value, 'page': page, 'page_size': PAGE_SIZE, 'mailto': CONTACT}
    url = BASE + '?' + urlencode(params)
    req = Request(url, headers={
        'Accept': 'application/json',
        'User-Agent': 'Academic-Publications-Audit/1.0 (contact: mario.barbareschi@unina.it)',
    })
    for attempt in range(3):
        try:
            with urlopen(req, timeout=timeout) as response:
                content_type = response.headers.get('Content-Type', '')
                payload = response.read(25 * 1024 * 1024)
                if 'json' not in content_type.lower() and not payload.lstrip().startswith(b'{'):
                    raise ValueError('Response was not JSON (' + content_type + '): ' + payload[:180].decode('utf-8', 'replace'))
                data = json.loads(payload)
                if not isinstance(data, dict) or not isinstance(data.get('results'), list):
                    raise ValueError('Unexpected API response structure')
                return data, url
        except HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                delay = min(10 * (2 ** attempt), 25)
                print(f'HTTP {exc.code}; retry in {delay}s', file=sys.stderr, flush=True)
                time.sleep(delay)
            else:
                raise RuntimeError(f'OpenAIRE HTTP {exc.code} for {url}') from exc
        except (URLError, TimeoutError) as exc:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                raise RuntimeError(f'OpenAIRE network error: {exc}') from exc


def collect(label, filter_value):
    all_rows = []
    total = None
    pages = 0
    query_url = ''
    for page in range(1, MAX_PAGES + 1):
        data, url = request_page(filter_value, page)
        if not query_url:
            query_url = url
        header = data.get('header') or {}
        if total is None:
            total = header.get('numFound')
        rows = data.get('results') or []
        all_rows.extend(rows)
        pages += 1
        print(f'{label}: page {page} / {total if total is not None else "?"} records reported; downloaded {len(all_rows)}', flush=True)
        if not rows:
            break
        if isinstance(total, int) and len(all_rows) >= total:
            break
        if len(rows) < PAGE_SIZE:
            # API may enforce a smaller page limit: use response's declared size.
            server_page_size = header.get('pageSize')
            if not isinstance(server_page_size, int) or server_page_size == 0:
                break
            if len(rows) < server_page_size:
                break
    return {'query': label, 'filter': filter_value, 'url': query_url,
            'reported_total': total, 'downloaded': len(all_rows), 'pages': pages,
            'truncated': pages >= MAX_PAGES and isinstance(total, int) and len(all_rows) < total,
            'rows': all_rows}


def summarize(raw_by_query):
    merged = {}
    for label, entry in raw_by_query.items():
        for row in entry['rows']:
            if not isinstance(row, dict):
                continue
            key = record_key(row)
            if key not in merged:
                merged[key] = {'record': row, 'queries': set()}
            merged[key]['queries'].add(label)
    publications = []
    excluded = []
    for item in merged.values():
        row = item['record']
        authors = names_authors(row)
        exact = [a for a in authors if author_match(a) == 'exact']
        initial = [a for a in authors if author_match(a) == 'initial-only']
        matching = exact or initial
        match_level = 'exact' if exact else ('initial-only' if initial else 'none')
        own_orcid = any(linked_orcid(a) == ORCID for a in matching)
        # The API can map ORCID to a different author or mark it pending.
        # An exact name is the safest first approximation, not an identity guarantee.
        if match_level == 'none':
            excluded.append({'title': row.get('mainTitle'), 'id': row.get('id'),
                             'queries': sorted(item['queries'])})
            continue
        date = row.get('publicationDate') or ''
        year = date[:4] if re.match(r'^\d{4}', date) else ''
        doi = get_doi(row)
        venue = ''
        for inst in row.get('instances') or []:
            if isinstance(inst, dict) and isinstance(inst.get('hostedBy'), dict):
                venue = clean(inst['hostedBy'].get('value', ''))
                if venue:
                    break
        authors_str = ', '.join(clean(a.get('fullName')) or
                                f"{clean(a.get('name'))} {clean(a.get('surname'))}".strip()
                                for a in authors)
        indicators = row.get('indicators') or {}
        impact = indicators.get('citationImpact') or {}
        cited = impact.get('citationCount')
        access = row.get('bestAccessRight') or {}
        if not isinstance(access, dict):
            access = {}
        publications.append({
            'year': year, 'title': clean(row.get('mainTitle')),
            'authors': authors_str, 'venue_or_repository': venue,
            'type': clean(row.get('type')), 'doi': doi,
            'doi_url': 'https://doi.org/' + doi if doi else '',
            'openaire_id': clean(row.get('id')),
            'openaire_url': 'https://explore.openaire.eu/search/result?id=' + str(row['id']) if row.get('id') else '',
            'open_access': clean(access.get('label')),
            'citations_reported': cited,
            'found_by': ', '.join(sorted(item['queries'])),
            'author_match': match_level,
            'orcid_on_matching_author': own_orcid,
            'needs_manual_review': (match_level != 'exact') or (not own_orcid),
        })
    publications.sort(key=lambda x: (x['year'], x['title'].casefold()), reverse=True)
    return publications, excluded


def export(folder, entries, publications, excluded):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    (folder / 'openaire_query_metadata.json').write_text(json.dumps({
        'generated_at_utc': now, 'author': AUTHOR, 'orcid': ORCID,
        'queries': [{k: v for k, v in e.items() if k != 'rows'} for e in entries.values()],
        'matched_records': len(publications), 'excluded_name_mismatch': len(excluded),
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'openaire_records.json').write_text(json.dumps({
        'generated_at_utc': now, 'source': 'OpenAIRE Graph API v4',
        'matched_publications': publications, 'excluded_name_mismatch': excluded,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'openaire_raw.json').write_text(json.dumps({
        'generated_at_utc': now,
        'queries': {k: v['rows'] for k, v in entries.items()},
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ['year', 'title', 'authors', 'venue_or_repository', 'type', 'doi',
              'doi_url', 'openaire_id', 'openaire_url', 'open_access',
              'citations_reported', 'found_by', 'author_match',
              'orcid_on_matching_author', 'needs_manual_review']
    with (folder / 'openaire_publications.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(publications)
    c = Counter(p['year'] for p in publications)
    exact = sum(x['author_match'] == 'exact' for x in publications)
    verified = sum(x['orcid_on_matching_author'] for x in publications)
    md = [
        '# OpenAIRE – Mario Barbareschi · Coverage audit', '',
        f'Downloaded (UTC): {now}',
        f'ORCID: `{ORCID}`',
        'Data source: OpenAIRE Graph API v4', '',
        '## Query coverage', '',
        '| Search | API total | Downloaded | Complete? |', '|---|---:|---:|---|',
    ]
    for e in entries.values():
        md.append(f"| {e['query']} | {e['reported_total']} | {e['downloaded']} | {'NO — page limit' if e['truncated'] else 'Yes'} |")
    md.extend(['', '## Quality checks', '',
        f'- Unique records mentioning Mario Barbareschi (exact or initial only): **{len(publications)}**',
        f'- With full given name Mario: **{exact}**',
        f'- With ORCID attributed to the matching author: **{verified}**',
        f'- Name mismatches excluded (potential false positives): **{len(excluded)}**',
        f'- Records requiring manual review (initial-only OR no ORCID on author): **{sum(p["needs_manual_review"] for p in publications)}**',
        '', 'These are OpenAIRE results, **not** a validated complete academic bibliography.',
        'They are not merged into the website. Please review the CSV before enabling any synchronization.',
        '', '## Count by year', '',
        '| Year | Records |', '|---|---:|'])
    for year, n in sorted(c.items(), reverse=True):
        md.append(f'| {year or "Not specified"} | {n} |')
    md.extend(['', '## Recent matching titles (first 25)', ''])
    for p in publications[:25]:
        md.append(f'- {p["year"]} — {p["title"]}' + (' [REVIEW]' if p['needs_manual_review'] else ''))
    md.extend(['', '## API queries', ''])
    for e in entries.values():
        md.append(f'- {e["query"]}: {e["url"]}')
    (folder / 'RIEPILOGO.md').write_text('\n'.join(md)+'\n', encoding='utf-8')


def main():
    argp = argparse.ArgumentParser()
    argp.add_argument('--output', default='openaire-export')
    args = argp.parse_args()
    queries = {
        'orcid': f'type:publication,authorships.author.orcid:{ORCID}',
        'author_name': f'type:publication,authorships.author.fullname:{AUTHOR}',
    }
    entries = {}
    errors = []
    for label, query in queries.items():
        try:
            entries[label] = collect(label, query)
        except Exception as exc:
            errors.append(f'{label}: {exc}')
            print('ERROR: ' + errors[-1], file=sys.stderr, flush=True)
    if not entries:
        print('FAILED: both OpenAIRE queries failed; no export created.', file=sys.stderr)
        return 1
    publications, excluded = summarize(entries)
    export(args.output, entries, publications, excluded)
    print(f'COMPLETE: {len(publications)} possible publications; {len(excluded)} excluded as name mismatch', flush=True)
    if errors:
        print('Partial export; one query failed: ' + '; '.join(errors), file=sys.stderr)
    print('Downloads are in ' + args.output, flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
