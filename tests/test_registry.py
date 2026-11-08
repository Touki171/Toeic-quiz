import copy
import datetime as dt
import json
import subprocess
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from registry import ROOT, validate, fingerprint
from build import generate

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((ROOT/'question-registry.json').read_text())
        self.today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    def errors(self):
        return '\n'.join(validate(self.data))
    def test_valid_original_content(self):
        self.assertEqual(validate(self.data),[])
        self.assertTrue(180<=len(self.data['passages'][0]['text'].split())<=250)
    def test_missing_history_flag(self):
        del self.data['historyComplete']
        self.assertIn('履歴が不完全', self.errors())
    def test_missing_date(self):
        del self.data['questions'][0]['publishedAt']
        self.assertIn('欠損',self.errors())
    def test_missing_collection(self):
        del self.data['passages']
        self.assertIn('配列',self.errors())
    def test_exact_duplicate(self):
        q=copy.deepcopy(self.data['questions'][0]); q['id']='duplicate'
        self.data['questions'].append(q)
        self.assertIn('完全一致',self.errors())
    def test_case_and_punctuation_duplicate(self):
        q=copy.deepcopy(self.data['questions'][0]);q['id']='duplicate';q['prompt']=q['prompt'].upper()+'!'
        q['options']=list(reversed(q['options']))
        self.data['questions'].append(q)
        self.assertIn('完全一致',self.errors())
    def test_same_prompt_changed_choices(self):
        q=copy.deepcopy(self.data['questions'][0]);q['id']='duplicate';q['options'][1]='approvals'
        self.data['questions'].append(q)
        self.assertIn('完全一致',self.errors())
    def test_duplicate_passage(self):
        p=copy.deepcopy(self.data['passages'][0]);p['id']='copy';self.data['passages'].append(p)
        self.assertIn('完全一致',self.errors())
    def similar(self):
        q=copy.deepcopy(self.data['questions'][0]);q['id']='similar';q['prompt']=q['prompt'].replace('warehouse','operations');self.data['questions'].append(q)
        return self.data['questions'][0],q
    def test_similarity_requires_review(self):
        self.similar()
        self.assertIn('要確認',self.errors())
    def test_review_is_bound_to_content(self):
        a,b=self.similar()
        self.data['similarityReviews']=[dict(ids=sorted([a['id'],b['id']]),fingerprints={a['id']:fingerprint(a),b['id']:fingerprint(b)},reviewer='Editor',reason='Different role, reviewed for content overlap',reviewedAt=str(self.today))]
        self.assertEqual(self.errors(),'')
        b['prompt']=b['prompt'].replace('operations','shipping')
        self.assertIn('要確認',self.errors())
    def test_review_cannot_override_exact_duplicate(self):
        a,b=self.similar();b['prompt']=a['prompt']
        self.data['similarityReviews']=[dict(ids=sorted([a['id'],b['id']]),fingerprints={a['id']:fingerprint(a),b['id']:fingerprint(b)},reviewer='Editor',reason='Approved',reviewedAt=str(self.today))]
        self.assertIn('完全一致',self.errors())
    def record_dates(self,gap):
        q=self.data['questions'][0];q['createdAt']=str(self.today-dt.timedelta(days=400));q['publicationDates']=[str(self.today-dt.timedelta(days=gap)),str(self.today)];q['publishedAt']=str(self.today)
    def test_182_days_blocked(self):
        self.record_dates(182);self.assertIn('183日未満',self.errors())
    def test_183_days_allowed(self):
        self.record_dates(183);self.assertEqual(self.errors(),'')
    def test_last_publication_controls_reuse(self):
        self.record_dates(182);q=self.data['questions'][0];q['publicationDates'].insert(0,str(self.today-dt.timedelta(days=370)))
        self.assertIn('183日未満',self.errors())
    def test_mismatched_latest_date(self):
        self.record_dates(183);self.data['questions'][0]['publishedAt']=None
        self.assertIn('不一致',self.errors())
    def test_incomplete_options_and_reasons(self):
        self.data['questions'][0]['options'].pop();self.data['questions'][0]['incorrectReasons'].pop('1')
        self.assertIn('4択',self.errors());self.assertIn('誤答3つ',self.errors())
    def test_invalid_passage_reference(self):
        self.data['questions'][1]['passageId']='missing';self.assertIn('参照',self.errors())
    def test_cannot_delete_archive(self):
        baseline=copy.deepcopy(self.data);self.data['questions'].pop()
        self.assertTrue(validate(self.data,baseline=baseline))
    def test_cannot_rewrite_existing_content(self):
        baseline=copy.deepcopy(self.data);self.data['questions'][0]['prompt']+=' Please choose.'
        self.assertIn('変更できません','\n'.join(validate(self.data,baseline=baseline)))
    def test_cannot_erase_publication_history(self):
        self.record_dates(183);baseline=copy.deepcopy(self.data)
        self.data['questions'][0]['publicationDates']=[];self.data['questions'][0]['publishedAt']=None
        self.assertIn('追記のみ','\n'.join(validate(self.data,baseline=baseline)))
    def test_release_stops_without_publication_dates(self):
        self.assertIn('当日の公開履歴','\n'.join(validate(self.data,release=str(self.today))))
    def test_release_with_complete_dates(self):
        for item in self.data['questions']+self.data['passages']:
            item['createdAt']=str(min(dt.date.fromisoformat(item['createdAt']),self.today))
            item['publishedAt']=str(self.today);item['publicationDates']=[str(self.today)]
        self.assertEqual(validate(self.data,release=str(self.today)),[])
    def test_release_date_not_arbitrary(self):
        self.assertIn('実行当日','\n'.join(validate(self.data,release=str(self.today-dt.timedelta(days=1)))))
    def test_static_html_no_javascript_dependency(self):
        page=generate(self.data,True)
        self.assertEqual(page.count('type="radio"'),16)
        self.assertEqual(page.count('class="explanation"'),4)
        self.assertEqual(page.count('class="outcome outcome-'),16)
        self.assertNotIn('<script',page)
        self.assertIn('width=device-width',page)
        self.assertNotIn('user-scalable=no',page)
        self.assertIn(':has(input:checked)',(ROOT/'styles.css').read_text())
        for q in self.data['questions']:
            for i in range(4):
                self.assertIn(f'id="{q["id"]}-{i}"',page)
                self.assertIn(f'for="{q["id"]}-{i}"',page)
            self.assertIn('正解：'+'ABCD'[q['answer']],page)
    def test_failed_release_removes_stale_output(self):
        (ROOT/'dist').mkdir(exist_ok=True);(ROOT/'dist'/'index.html').write_text('stale')
        result=subprocess.run([sys.executable,str(ROOT/'scripts/build.py'),'--release',str(self.today)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((ROOT/'dist').exists())

if __name__=='__main__':
    unittest.main()
