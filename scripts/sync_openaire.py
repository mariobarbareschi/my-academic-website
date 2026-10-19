#!/usr/bin/env python3
"""Synchronize all Mario Barbareschi OpenAIRE matches into the public site.

The API is queried by ORCID and by name, with full pagination. All records
matching Mario Barbareschi or M. Barbareschi are included (including those
without the ORCID on the author). Records whose author names do not match are
excluded. Existing DBLP keys and selected-publication IDs are preserved.

A local export can be imported with --input; it never calls the Internet.
No third-party dependencies.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import unescape
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

from export_openaire import (AUTHOR, ORCID, collect, summarize)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'site' / 'data' / 'publications.json'


def clean(value):
    text = str(value or '')
    # Some aggregators store already escaped text, then escape it again.
    for _ in range(5):
        decoded = unescape(text)
        if decoded == text:
            break
        text = decoded
    return ' '.join(text.split())


def compact_title(value):
    value = unicodedata.normalize('NFKD', clean(value)).casefold()
    return ''.join(c for c in value if c.isalnum() and not unicodedata.combining(c))


def title_id(item):
    return (compact_title(item.get('title')), int(item.get('year') or 0))


def doi_id(item):
    doi = clean(item.get('doi_url')).casefold()
    doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
    return doi.strip('/. ') if doi else ''


def canonical_name(name):
    name = clean(name)
    # OpenAIRE sometimes lists names in citation order: "Surname, Firstname".
    if name.count(',') == 1:
        surname, given = [s.strip() for s in name.split(',', 1)]
        if surname and given:
            return f'{given} {surname}'
    return name


def author_names(row):
    authors = row.get('authors') or []
    if not isinstance(authors, list):
        return []
    names = [canonical_name(a.get('fullName') or
                            ' '.join([a.get('name') or '', a.get('surname') or '']))
             for a in authors if isinstance(a, dict)]
    return [n for n in names if n]


def fallback_authors(value):
    text = clean(value)
    tokens = [s.strip() for s in text.split(',') if s.strip()]
    # If an ORCID export uses reversed names, convert pairs to display names.
    if (len(tokens) >= 2 and len(tokens) % 2 == 0 and
            re.search(r'\bBarbareschi\s*,\s*(?:Mario|M\.)\b', text, flags=re.I)):
        return [f'{tokens[i+1]} {tokens[i]}' for i in range(0, len(tokens), 2)]
    return tokens


def raw_lookup(entries):
    result = {}
    for entry in entries.values():
        for row in entry.get('rows', []):
            if isinstance(row, dict):
                key = compact_title(row.get('mainTitle'))
                if key and (key not in result or len(row.get('authors') or []) > len(result[key].get('authors') or [])):
                    result[key] = row
    return result


def venue_name(record):
    venue = clean(record.get('venue_or_repository'))
    # OpenAIRE's hostedBy is a repository, not necessarily a journal/venue.
    bad = {'unknown repository', 'hal', 'inria2', 'zenodo',
           'fedoa - iris università degli studi napoli federico ii'}
    return '' if venue.casefold() in bad else venue


def kind_name(record, raw):
    # OpenAIRE uses type='publication' for every result, so inspect instances.
    instances = raw.get('instances') or []
    kinds = [clean(x.get('type')).lower() for x in instances if isinstance(x, dict)]
    if any('conference' in k for k in kinds):
        return 'Conference'
    if any('journal' in k for k in kinds):
        return 'Journal'
    # 'Article' includes deposited conference papers; don't mislabel them.
    return 'Other'


def transform(records, entries=None):
    by_title = raw_lookup(entries or {})
    results = []
    seen = set()
    for record in records:
        title = clean(record.get('title'))
        year = str(record.get('year') or '').strip()
        if not title or not year.isdigit():
            continue
        year = int(year)
        if not (1950 <= year <= datetime.now(timezone.utc).year + 3):
            continue
        origin = clean(record.get('openaire_id'))
        doi = clean(record.get('doi_url'))
        identifier = origin or doi or (title + str(year))
        key = 'openaire/' + hashlib.sha256(identifier.encode('utf-8')).hexdigest()[:20]
        if key in seen:
            continue
        seen.add(key)
        raw = by_title.get(compact_title(title), {})
        authors = author_names(raw) or fallback_authors(record.get('authors'))
        if not authors:
            continue
        publication = {
            'key': key,
            'title': title,
            'authors': authors,
            'year': year,
            'type': kind_name(record, raw),
            'venue': venue_name(record),
            'dblp_url': None,
            'doi_url': doi if doi.startswith('https://doi.org/') else None,
            'pdf_url': None,
            'openaire_url': clean(record.get('openaire_url')) or None,
            'openaire_id': origin,
        }
        results.append(publication)
    return sorted(results, key=lambda p: (-p['year'], p['title'].casefold()))


def merge(previous, incoming):
    """Retain existing keys; match DOI first, then normalized title + year."""
    existing = previous.get('publications', []) if isinstance(previous, dict) else []
    result = [dict(p) for p in existing if isinstance(p, dict) and p.get('key') and p.get('title')]
    for p in result:
        p['title'] = clean(p['title'])
    by_key = {p['key']: p for p in result}
    by_doi = {doi_id(p): p for p in result if doi_id(p)}
    by_title = {title_id(p): p for p in result}
    added = 0
    for entry in incoming:
        found = by_key.get(entry['key'])
        if found is None and doi_id(entry):
            found = by_doi.get(doi_id(entry))
        if found is None:
            found = by_title.get(title_id(entry))
        if found is not None:
            # Never replace carefully edited DBLP display information.
            for field in ('doi_url', 'pdf_url', 'openaire_url', 'openaire_id'):
                if not found.get(field) and entry.get(field):
                    found[field] = entry[field]
            for field in ('venue', 'type', 'authors'):
                if not found.get(field) and entry.get(field):
                    found[field] = entry[field]
        else:
            result.append(dict(entry))
            by_key[entry['key']] = result[-1]
            if doi_id(entry):
                by_doi[doi_id(entry)] = result[-1]
            by_title[title_id(entry)] = result[-1]
            added += 1
    result.sort(key=lambda p: (-int(p.get('year') or 0), clean(p.get('title')).casefold()))
    return result, added


def download_records():
    queries = {
        'orcid': f'type:publication,authorships.author.orcid:{ORCID}',
        'author_name': f'type:publication,authorships.author.fullname:{AUTHOR}',
    }
    entries = {}
    for label, query in queries.items():
        entry = collect(label, query)
        total = entry.get('reported_total')
        downloaded = entry.get('downloaded')
        if entry.get('truncated') or not isinstance(total, int) or total < 1 or downloaded != total:
            raise RuntimeError(f'Incomplete OpenAIRE query {label}: downloaded={downloaded}, total={total}')
        entries[label] = entry
    records, excluded = summarize(entries)
    print(f'OpenAIRE: {len(records)} distinct matching records; {len(excluded)} author name mismatches excluded.', flush=True)
    return records, entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Import a previously downloaded OpenAIRE records JSON')
    parser.add_argument('--raw', type=Path, help='Optional raw OpenAIRE export for author names/types')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--min-records', type=int, default=70)
    args = parser.parse_args()
    try:
        if args.input:
            obj = json.loads(args.input.read_text(encoding='utf-8'))
            records = obj.get('matched_publications', [])
            if not isinstance(records, list):
                raise ValueError('Invalid OpenAIRE export: matched_publications is not an array')
            entries = {}
            if args.raw:
                raw_obj = json.loads(args.raw.read_text(encoding='utf-8'))
                entries = {k: {'rows': v} for k, v in raw_obj.get('queries', {}).items()}
            # The snapshot's actual download date, not the local import time.
            timestamp = obj.get('generated_at_utc')
        else:
            records, entries = download_records()
            timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        if len(records) < args.min_records:
            raise ValueError(f'Only {len(records)} OpenAIRE matches (minimum {args.min_records}); preserving existing data')
        papers = transform(records, entries)
        if len(papers) < args.min_records:
            raise ValueError(f'Only {len(papers)} valid publications after conversion; preserving existing data')
        old = json.loads(args.output.read_text(encoding='utf-8')) if args.output.exists() else {}
        merged, added = merge(old, papers)
        updated = dict(old)
        updated.update({
            'source': 'openaire+cached-dblp',
            'author_pid': '134/1019',
            'orcid': ORCID,
            'last_synced_utc': timestamp,
            'bootstrap_only': False,
            'publications': merged,
        })
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: incomplete API responses or malformed exports never replace the site.
        temp = args.output.with_suffix('.json.tmp')
        try:
            temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            temp.replace(args.output)
        finally:
            if temp.exists():
                temp.unlink()
        print(f'Source: OpenAIRE; processed {len(papers)} matches, added {added}, published {len(merged)} records to {args.output}.', flush=True)
        return 0
    except Exception as exc:
        print('OpenAIRE synchronization aborted; existing bibliography preserved: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
