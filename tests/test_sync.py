import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sync_dblp import parse_person_xml

EXAMPLE=b'''<?xml version="1.0" encoding="utf-8"?>
<dblpperson name="Mario Barbareschi" pid="134/1019">
  <r><article key="journals/test/Example26"><author>Mario Barbareschi</author><author>Colleague Example</author><title>Hardware &amp; Software for Embedded AI.</title><pages>1-10</pages><year>2026</year><journal>Test Journal</journal><ee>https://doi.org/10.0000/example</ee></article></r>
  <r><inproceedings key="conf/test/Example25"><author>Mario Barbareschi</author><title>Conference Work</title><booktitle>TestConf</booktitle><year>2025</year></inproceedings></r>
  <r><www key="homepages/134/1019"><author>Mario Barbareschi</author><title>Mario Barbareschi</title></www></r>
</dblpperson>'''

class PersonXMLTest(unittest.TestCase):
    def test_xml_extracts_and_classifies(self):
        pubs=parse_person_xml(EXAMPLE)
        self.assertEqual(len(pubs),2)
        self.assertEqual(pubs[0]['title'],'Hardware & Software for Embedded AI.')
        self.assertEqual(pubs[0]['doi_url'],'https://doi.org/10.0000/example')
        self.assertEqual(pubs[0]['type'],'Journal')
        self.assertEqual(pubs[1]['type'],'Conference')
        self.assertEqual(pubs[1]['authors'],['Mario Barbareschi'])
        self.assertEqual(pubs[0]['key'],'journals/test/Example26')
    def test_no_duplicate_keys(self):
        xml=EXAMPLE.replace(b'</dblpperson>',b'<r><article key="journals/test/Example26"><title>Duplicated</title><year>2025</year></article></r></dblpperson>')
        self.assertEqual(len(parse_person_xml(xml)),2)

if __name__=='__main__':unittest.main()
