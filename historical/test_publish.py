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
            rec={'tag':'v1.0.0','upstream_repository':publish.UPSTREAM,'upstream_source':publish.SOURCES['v1.0.0'],'product_source':publish.SOURCES['v1.0.0'],'build_tooling_source':'a'*40,'source_modifications':[],'platform':plat,'variant':var,'run_id':'123','run_attempt':'1','filename':name,'host':'PlotJuggler 3.9.2','host_source':{'repository':'PlotJuggler/PlotJuggler','tag':'3.9.2','commit':'d115b540c4f2664259a594259b9e11595f0263fc'},'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
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
    def test_original_matrix_lengths(self):
        self.assertEqual(len(publish.matrix('v1.0.0')),2)
        self.assertEqual(len(publish.matrix('v1.1.0')),3)


from unittest.mock import patch
import copy
class PromotionGuards(unittest.TestCase):
    def setUp(self):
        self.sha='a'*40
        self.responses={
          'actions/runs/123':{'id':123,'run_attempt':1,'head_sha':self.sha,'head_branch':'main-ci/upstream-tag-builds','path':'.github/workflows/upstream-tags.yml','status':'completed','conclusion':'success','event':'push','repository':{'full_name':publish.REPO}},
          'actions/runs/123/jobs?per_page=100':{'total_count':7,'jobs':[{'name':n,'conclusion':'success'} for n in sorted({'PlotJuggler (ubuntu-22.04)','PlotJuggler (windows-2022)'} | {f'{t} {plat} {var}' for t in publish.SOURCES for plat,var in publish.matrix(t)})]},
          'git/ref/tags/v1.0.0':{'object':{'type':'commit','sha':publish.SOURCES['v1.0.0']}},
          'releases?per_page=100':[], 'releases/latest':{'tag_name':'v1.2.0'}}
    def rejected(self):
        with patch.dict('os.environ',{'GITHUB_REPOSITORY':publish.REPO}), patch.object(publish,'api',side_effect=lambda p,repo=publish.REPO:copy.deepcopy(self.responses[p])),patch.object(publish,'gh') as gh:
            with self.assertRaises(ValueError):publish.publish(123,self.sha,'v1.0.0')
            gh.assert_not_called()  # No artifact download, release write or tag action.
    def test_wrong_build_source(self):
        self.responses['actions/runs/123']['head_sha']='b'*40;self.rejected()
    def test_wrong_branch(self):
        self.responses['actions/runs/123']['head_branch']='main';self.rejected()
    def test_running_candidate(self):
        self.responses['actions/runs/123']['status']='in_progress';self.rejected()
    def test_wrong_repository(self):
        self.responses['actions/runs/123']['repository']['full_name']='other/repo';self.rejected()
    def test_missing_named_job(self):
        self.responses['actions/runs/123/jobs?per_page=100']['jobs'][0]['name']='other';self.rejected()
    def test_wrong_workflow(self):
        self.responses['actions/runs/123']['path']='.github/workflows/build.yml';self.rejected()
    def test_untrusted_pr_run(self):
        self.responses['actions/runs/123']['event']='pull_request';self.rejected()
    def test_failed_candidate(self):
        self.responses['actions/runs/123']['conclusion']='failure';self.rejected()
    def test_incomplete_job_matrix(self):
        self.responses['actions/runs/123/jobs?per_page=100']['total_count']=6;self.rejected()
    def test_failed_plugin_job(self):
        self.responses['actions/runs/123/jobs?per_page=100']['jobs'][0]['conclusion']='failure';self.rejected()
    def test_moved_original_tag(self):
        self.responses['git/ref/tags/v1.0.0']['object']['sha']='b'*40;self.rejected()
    def test_existing_release(self):
        self.responses['releases?per_page=100']=[{'tag_name':'v1.0.0'}];self.rejected()
    def test_latest_changed(self):
        self.responses['releases/latest']['tag_name']='v1.1.0';self.rejected()

if __name__=='__main__':unittest.main()
