"""Tests for the PACKAGING helper only; not quant-research tests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from check_delivery import verify, digest, local_file

class EvidenceCheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'evidence.txt').write_text('Synthetic evidence: this is not a trading result.',encoding='utf-8')
        self.r={'schema_version':'1.0','stage_id':'C0','run_state':'completed',
                'engineering_state':'pending','research_state':'not_evaluated',
                'implementer_id':'synthetic-I','reviewer_id':None,
                'authorization_reference':'SYNTHETIC_TEST_ONLY','code_commit':'a'*40,
                'contract_sha256':'b'*64,
                'evidence':[{'id':'ev','path':'evidence.txt','kind':'log','sha256':digest(self.root/'evidence.txt')}],
                'checks':[{'gate_id':f'C0-{i:02}','status':'PASS','evidence_ids':['ev']} for i in range(1,9)],
                'open_issues':[],'run_records':[],'next_stage_authorized':False}
    def failed(self, report=None):
        self.assertEqual(verify(report or self.r,self.root)['status'],'EVIDENCE_CHECK_FAILED')
    def test_complete_synthetic_files_only(self):
        result=verify(self.r,self.root)
        self.assertEqual(result['status'],'EVIDENCE_FILES_OK')
        self.assertFalse(result['engineering_approval_granted'])
        self.assertFalse(result['research_validated'])
    def test_template_does_not_pass(self):
        self.r['run_state']='not_started'; self.failed()
    def test_hash_tamper(self):
        (self.root/'evidence.txt').write_text('tampered'); self.failed()
    def test_missing_file(self):
        (self.root/'evidence.txt').unlink(); self.failed()
    def test_traversal_rejected(self):
        with self.assertRaises(ValueError): local_file(self.root,'../outside')
    def test_windows_absolute_rejected(self):
        with self.assertRaises(ValueError): local_file(self.root,'D:\\secret.txt')
    def test_missing_gate(self):
        self.r['checks'].pop(); self.failed()
    def test_duplicate_gate(self):
        self.r['checks'].append(self.r['checks'][0]); self.failed()
    def test_unknown_evidence_reference(self):
        self.r['checks'][0]['evidence_ids']=['unknown']; self.failed()
    def test_blocker(self):
        self.r['open_issues']=[{'issue_id':'bad','severity':'CRITICAL','status':'open'}]; self.failed()
    def test_self_review_rejected(self):
        self.r['engineering_state']='accepted'
        self.r['reviewer_id']='synthetic-I'; self.failed()
    def test_junit_failure(self):
        p=self.root/'tests.xml'
        p.write_text('<testsuite><testcase name="x"><failure>no</failure></testcase></testsuite>')
        self.r['evidence'].append({'id':'jt','path':'tests.xml','kind':'junit','sha256':digest(p)})
        self.failed()
    def test_junit_skip_not_hidden(self):
        p=self.root/'tests.xml'
        p.write_text('<testsuite><testcase name="x"><skipped/></testcase></testsuite>')
        self.r['evidence'].append({'id':'jt','path':'tests.xml','kind':'junit','sha256':digest(p)})
        self.failed()
    def test_fabricated_junit_counts_without_cases(self):
        p=self.root/'tests.xml'; p.write_text('<testsuite tests="703" failures="0"/>')
        self.r['evidence'].append({'id':'jt','path':'tests.xml','kind':'junit','sha256':digest(p)})
        self.failed()
    def test_non_c0_requires_run(self):
        self.r['stage_id']='C1'
        self.r['checks']=[{'gate_id':f'C1-{i:02}','status':'PASS','evidence_ids':['ev']} for i in range(1,9)]
        self.failed()
    def test_run_hash_change(self):
        run={'status':'completed','exit_code':0,'command':['python','synthetic.py'],
             'started_at_utc':'2026-09-22T00:00:00+00:00','ended_at_utc':'2026-09-22T00:00:01+00:00',
             'code_sha256_at_start':'c'*64,'code_sha256_at_end':'d'*64,
             'config_sha256_at_start':'e'*64,'config_sha256_at_end':'e'*64,
             'expected_arms':[],'actual_arms':[]}
        p=self.root/'run.json'; p.write_text(json.dumps(run))
        self.r['evidence'].append({'id':'run','path':'run.json','kind':'run_record','sha256':digest(p)})
        self.r['run_records']=['run']; self.failed()

if __name__=='__main__':
    unittest.main(verbosity=2)
