#!/usr/bin/env python3
"""Refresh the local academic bibliography from a DBLP person-XML export.

Uses only the Python standard library. Refuses to overwrite the last good
bibliography on download, parsing, or unusually-small-export failures.
"""
import argparse
from datetime import datetime, timezone
from html import unescape, entities
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

DEFAULT_XML='https://dblp.org/pid/134/1019.xml'
DEFAULT_OUT=Path(__file__).resolve().parents[1]/'site/data/publications.json'


def flat(element):
    if element is None: return ''
    return ' '.join(unescape(''.join(element.itertext())).split()).strip()


def first(node, *names):
    for name in names:
        child=node.find(name)
        if child is not None and flat(child):return flat(child)
    return ''


def url_or_none(value):
    if not value: return None
    value=value.strip()
    return value if value.startswith('https://') else None


def decode_named_entities(xml_data):
    """Convert DBLP DTD's named Latin entities without touching XML &amp;, etc."""
    xml_text = xml_data.decode('utf-8', errors='replace') if b'encoding="utf-8"' in xml_data[:200].lower() else None
    if xml_text is None:
        # Respect an XML encoding declaration where present.
        match = re.search(br'<\?xml[^>]*encoding=["\']([^"\']+)', xml_data[:200], flags=re.I)
        charset = match.group(1).decode('ascii') if match else 'utf-8'
        xml_text = xml_data.decode(charset, errors='replace')
    def subst(m):
        name=m.group(1)
        if name in ('amp','lt','gt','quot','apos'): return m.group(0)
        codepoint=entities.name2codepoint.get(name)
        return '&#'+str(codepoint)+';' if codepoint else m.group(0)
    xml_text=re.sub(r'&([A-Za-z][A-Za-z0-9]+);',subst,xml_text)
    # The XML declaration can still refer to the original byte encoding. By
    # returning Unicode text, ElementTree will not decode it a second time.
    return xml_text


def parse_person_xml(xml_data):
    # DBLP's per-person export has <dblpperson><r><article|inproceedings... />.
    root=ET.fromstring(decode_named_entities(xml_data))
    publications=[]
    records=[r[0] for r in root.findall('.//r') if len(r)]
    if not records:
        records=[node for node in root if node.tag in ('article','inproceedings','proceedings','incollection','book','phdthesis','mastersthesis','www')]
    seen=set()
    for record in records:
        kind=record.tag.split('}')[-1]
        key=record.get('key','')
        if not key or key in seen: continue
        title=first(record,'title')
        year_str=first(record,'year')
        if not title or not year_str.isdigit():continue
        year=int(year_str)
        if year<1950 or year>datetime.now(timezone.utc).year+3:continue
        authors=[flat(x) for x in record.findall('author')]
        if not authors: authors=[flat(x) for x in record.findall('editor')]
        typ='Journal' if kind=='article' else 'Conference' if kind in ('inproceedings','proceedings') else 'Other'
        venue=first(record,'journal','booktitle','school','publisher','series')
        volume=first(record,'volume'); number=first(record,'number'); pages=first(record,'pages')
        venue=', '.join([v for v in [venue, volume and ('vol. '+volume), number and ('no. '+number), pages and ('pp. '+pages)] if v])
        ee=[flat(e) for e in record.findall('ee')]
        doi=next((v for v in ee if v.startswith('https://doi.org/')),None)
        if not doi:
            doi_text=first(record,'doi')
            if doi_text: doi='https://doi.org/'+doi_text.removeprefix('https://doi.org/')
        pdf=next((v for v in ee if v.lower().split('?')[0].endswith('.pdf')),None)
        publications.append({'key':key,'title':title,'authors':authors,'year':year,'type':typ,'venue':venue,
                             'dblp_url':'https://dblp.org/rec/'+key,
                             'doi_url':url_or_none(doi),'pdf_url':url_or_none(pdf)})
        seen.add(key)
    publications.sort(key=lambda p:(-p['year'],p['key']))
    return publications


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,help='Optional local XML file (offline testing)')
    parser.add_argument('--output',type=Path,default=DEFAULT_OUT)
    parser.add_argument('--min-records',type=int,default=20,help='Safety threshold, prevents accidental data loss')
    args=parser.parse_args()
    try:
        if args.input: xml_data=args.input.read_bytes()
        else:
            req=Request(DEFAULT_XML,headers={'User-Agent':'MarioBarbareschiAcademicWebsite/1.0 (DBLP person bibliography)', 'Accept':'application/xml,text/xml'})
            with urlopen(req,timeout=40) as resp:
                xml_data=resp.read()
        papers=parse_person_xml(xml_data)
        if len(papers)<args.min_records:
            raise ValueError(f'Only {len(papers)} publications parsed (expected at least {args.min_records}); keeping existing data.')
        if args.output.exists():
            try:
                previous=json.loads(args.output.read_text(encoding='utf-8'))
                if previous.get('bootstrap_only') is False and previous.get('publications')==papers:
                    print(f'DBLP checked: {len(papers)} publications; no metadata changes.')
                    return 0
            except (ValueError, OSError):
                pass
        payload={'source':'dblp','author_pid':'134/1019','last_synced_utc':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                 'bootstrap_only':False,'publications':papers}
        dest=args.output
        dest.parent.mkdir(parents=True,exist_ok=True)
        temp=dest.with_name(dest.name+'.tmp')
        temp.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        temp.replace(dest)
        print(f'Synchronized {len(papers)} DBLP records into {dest}')
    except Exception as exc:
        print(f'DBLP synchronization aborted; existing bibliography preserved: {exc}',file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
