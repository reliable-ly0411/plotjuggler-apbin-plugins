import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import publish

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.run={'head_sha':'a'*40,'id':123,'run_attempt':1}
        for plat,var in publish.matrix('v1.0.0'):
            folder=self.root/f'historical-v1.0.0-{plat}-{var}';folder.mkdir()
            name=publish.asset_name('v1.0.0',plat,var)
            data=b'\x7fELF-test-'+var.encode();(folder/name).write_bytes(data)
            rec={'tag':'v1.0.0','upstream_repository':publish.UPSTREAM,'upstream_source':publish.SOURCES['v1.0.0'],'product_source':publish.SOURCES['v1.0.0'],'build_tooling_source':'a'*40,'source_modifications':[],'platform':plat,'variant':var,'run_id':'123','run_attempt':'1','filename':name,'host':'PlotJuggler 3.9.2','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            (folder/'SOURCE.json').write_text(json.dumps(rec))
    def modify(self,key,value):
        f=self.root/'historical-v1.0.0-ubuntu-22.04-no_units/SOURCE.json';r=json.loads(f.read_text());r[key]=value;f.write_text(json.dumps(r))
    def test_collect_complete_matrix(self):
        hashes=publish.collect('v1.0.0',self.root,self.root/'assets',self.run)
        self.assertEqual(set(hashes),{'libDataAPBin_no_units_v1.0.0.so','libDataAPBin_with_units_v1.0.0.so','README-licenses.txt'})
    def test_source_mismatch(self):
        self.modify('product_source','b'*40)
        with self.assertRaises(ValueError):publish.collect('v1.0.0',self.root,self.root/'assets',self.run)
    def test_attempt_mismatch(self):
        self.modify('run_attempt','2')
        with self.assertRaises(ValueError):publish.collect('v1.0.0',self.root,self.root/'assets',self.run)
    def test_modified_product_rejected(self):
        self.modify('source_modifications',['parser.cpp'])
        with self.assertRaises(ValueError):publish.collect('v1.0.0',self.root,self.root/'assets',self.run)
    def test_tampered_binary_rejected(self):
        self.modify('sha256','0'*64)
        with self.assertRaises(ValueError):publish.collect('v1.0.0',self.root,self.root/'assets',self.run)
    def test_latest_and_tag_validation_before_download(self):
        self.assertEqual(len(publish.matrix('v1.0.0')),2)
        self.assertEqual(len(publish.matrix('v1.1.0')),3)
if __name__=='__main__':unittest.main()
