"""Offline checks for OpenAIRE import, de-duplication and data preservation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sync_openaire as sync


class OpenAireSiteTests(unittest.TestCase):
    def test_author_display(self):
        self.assertEqual(sync.canonical_name('Barbareschi, Mario'), 'Mario Barbareschi')
        self.assertEqual(sync.canonical_name('Mario Barbareschi'), 'Mario Barbareschi')

    def test_doi_and_title_matching(self):
        old = {'publications': [dict(key='journals/test/1', title='Foo: Deep Learning', year=2025,
                                     authors=['Mario Barbareschi'], type='Journal', venue='Example J.',
                                     doi_url=None, dblp_url='https://dblp.org/rec/journals/test/1')]}
        new = [dict(key='openaire/a', title='Foo Deep Learning', year=2025, authors=['Mario Barbareschi'],
                    doi_url='https://doi.org/10.1234/foo', openaire_url='https://explore.openaire.eu/a')]
        merged, added = sync.merge(old, new)
        self.assertEqual(added, 0)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['key'], 'journals/test/1')
        self.assertEqual(merged[0]['venue'], 'Example J.')
        self.assertEqual(merged[0]['doi_url'], 'https://doi.org/10.1234/foo')

    def test_non_dblp_records_do_not_get_dblp_key(self):
        item = {'title': 'A sample paper', 'year': '2025', 'authors': 'Mario Barbareschi',
                'openaire_id': 'doi____::abcdef', 'openaire_url': 'https://explore.openaire.eu/a',
                'doi_url': '', 'venue_or_repository': 'Unknown Repository'}
        entries = {'orcid': {'rows': [{'mainTitle': 'A sample paper',
                      'authors': [{'fullName': 'Barbareschi, Mario'}],
                      'instances': [{'type': 'Article'}]}]}}
        results = sync.transform([item], entries)
        self.assertEqual(results[0]['authors'], ['Mario Barbareschi'])
        self.assertTrue(results[0]['key'].startswith('openaire/'))
        self.assertEqual(results[0]['venue'], '')
        self.assertEqual(results[0]['type'], 'Other')

    def test_incomplete_query_refuses_update(self):
        fake = {'query': 'orcid', 'reported_total': 101, 'downloaded': 99, 'truncated': False, 'rows': []}
        with patch.object(sync, 'collect', return_value=fake):
            with self.assertRaisesRegex(RuntimeError, 'Incomplete OpenAIRE query'):
                sync.download_records()

    def test_bad_snapshot_does_not_write(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'publications.json'
            original = {'publications': [{'key': 'x', 'title': 'Keep'}]}
            target.write_text(json.dumps(original), encoding='utf-8')
            source = Path(folder) / 'bad.json'
            source.write_text(json.dumps({'matched_publications': []}), encoding='utf-8')
            argv = ['sync_openaire.py', '--input', str(source), '--output', str(target), '--min-records', '70']
            with patch.object(sys, 'argv', argv):
                self.assertEqual(sync.main(), 1)
            self.assertEqual(json.loads(target.read_text()), original)


if __name__ == '__main__':
    unittest.main()
