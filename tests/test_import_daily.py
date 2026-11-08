import copy
import datetime as dt
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from import_daily import import_package

class ImportDailyTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads((ROOT / 'question-registry.json').read_text())
        date = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
        passage = copy.deepcopy(self.base['passages'][0]); passage.update(id='daily-new-passage',createdAt=date)
        questions = copy.deepcopy(self.base['questions'])
        for i, q in enumerate(questions):
            q['id'] = f'daily-new-q{i}'
            q['createdAt'] = date
            q['prompt'] += ' new'
            if q['part'] == 7: q['passageId'] = 'daily-new-passage'
        passage['text'] += ' New'
        self.pkg = {'slot':'0700','passages':[passage],'questions':questions}

    def test_duplicate_content_rejected(self):
        # Near-duplicate to existing source is rejected by the shared validator.
        with self.assertRaisesRegex(ValueError, '台帳検査'):
            import_package(self.base,self.pkg)

    def test_invalid_slot(self):
        self.pkg['slot']='1300'
        with self.assertRaisesRegex(ValueError, 'slot'):
            import_package(self.base,self.pkg)

    def test_existing_id(self):
        self.pkg['questions'][0]['id']=self.base['questions'][0]['id']
        with self.assertRaisesRegex(ValueError, 'ID'):
            import_package(self.base,self.pkg)

    def test_no_publication_dates(self):
        self.pkg['questions'][0]['publicationDates']=['2026-11-08']
        with self.assertRaisesRegex(ValueError, '未公開'):
            import_package(self.base,self.pkg)

if __name__=='__main__': unittest.main()
