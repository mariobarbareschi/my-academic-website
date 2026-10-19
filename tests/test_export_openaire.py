import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from export_openaire import author_match, get_doi, summarize, record_key

class TestOpenAire(unittest.TestCase):
    def test_full_name(self):
        self.assertEqual(author_match({'fullName': 'Barbareschi, Mario'}), 'exact')
        self.assertEqual(author_match({'fullName': 'Mario Barbareschi'}), 'exact')
        self.assertEqual(author_match({'fullName': 'M. Barbareschi'}), 'initial-only')
        self.assertEqual(author_match({'fullName': 'Mario Rossi'}), 'none')
    def test_doi(self):
        self.assertEqual(get_doi({'instances': [{'alternateIdentifiers':[{'scheme':'doi','value':'10.1109/TEST.123'}]}]}),'10.1109/test.123')
    def test_filter_and_dedup(self):
        right={'id':'id1','mainTitle':'Example study','publicationDate':'2025-02-01','authors':[{'fullName':'Mario Barbareschi','pid':{'id':{'scheme':'orcid','value':'0000-0002-1417-6328'}}}]}
        wrong={'id':'id2','mainTitle':'Unrelated','authors':[{'fullName':'Mario Rossi','pid':{'id':{'scheme':'orcid_pending','value':'0000-0002-1417-6328'}}}]}
        data={'orcid':{'rows':[right,wrong]},'author_name':{'rows':[right]}}
        included,excluded=summarize(data)
        self.assertEqual(len(included),1)
        self.assertEqual(len(excluded),1)
        self.assertEqual(included[0]['found_by'],'author_name, orcid')
        self.assertFalse(included[0]['needs_manual_review'])

if __name__=='__main__':
    unittest.main()
