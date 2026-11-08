import copy
import datetime as dt
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from import_daily import import_package
from registry import validate

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


    def valid_package(self, created=None):
        """Independent unpublished items, not near-copies of the archive."""
        package = copy.deepcopy(self.pkg)
        passage = package['passages'][0]
        passage['text'] = """Riverbend Gallery is inviting local residents to help prepare its annual exhibition of handmade maps. This year, the exhibition will explore how people remember places that have changed. Contributors do not need professional drawing experience. A simple sketch of a street, a park, or a building is welcome if it includes a short explanation of why that location matters to the artist.

Completed maps should reach the gallery by March 14. Staff will photograph every submission before arranging the display, so visitors can later browse a digital collection. Original pieces will be returned after the exhibition closes in April. Contributors who prefer to remain anonymous should attach a separate note with their contact details rather than sign the front of their work.

The gallery has also arranged a free materials session for anyone who needs paper or colored pencils. Supplies will be distributed on Saturday morning while stocks last. No registration is required, but each person may collect only one packet. Volunteers will be available to discuss ideas, although they cannot complete drawings for participants. Questions about sending large or fragile pieces should be directed to exhibition assistant Leon Wu before delivery."""
        passage['title'] = 'A neighborhood map exhibition'
        passage['translation'] = 'Riverbend Galleryは地域の記憶を描く地図を募集。締切は3月14日、原画は4月の閉幕後に返却します。画材は土曜朝に1人1組配布します。'
        prompts = [
            'Visitors can examine the restored sculpture more ______ under the new lighting.',
            'When must contributors send their completed maps to the gallery?',
            'How will original artworks be handled once the exhibition ends?',
            'Which restriction applies to the free materials session?'
        ]
        options = [
            ['clearly', 'clear', 'clarity', 'clearness'],
            ['After the April closing', 'By March 14', 'Before Saturday breakfast', 'On the final exhibition day'],
            ['They will be sold to visitors', 'They will stay in a permanent archive', 'They will be returned to contributors', 'They will be replaced with pencils'],
            ['Visitors must register online', 'Only professional artists may attend', 'Volunteers must finish every drawing', 'Each visitor may receive just one packet']
        ]
        translations = [
            '来館者は新しい照明の下で修復した彫刻をよりはっきり鑑賞できます。',
            '完成した地図をいつまでに送る必要がありますか？',
            '展示終了後に原画はどうなりますか？',
            '無料画材配布にはどの制限がありますか？'
        ]
        evidence = ['動詞examineを修飾する副詞clearlyが必要です。', '第2段落で締切をMarch 14としています。', '原画は4月の閉幕後に返すと記されています。', '最後の段落で1人1組としています。']
        for i, q in enumerate(package['questions']):
            q.update(prompt=prompts[i], options=options[i], answer=i,
                     translation=translations[i], evidence=evidence[i],
                     optionTranslations=[["はっきりと", "明確な", "明確さ", "明瞭さ"],
                                         ["4月の閉幕後", "3月14日まで", "土曜の朝食前", "展示最終日"],
                                         ["来館者に売却", "永久保存", "出品者に返却", "鉛筆と交換"],
                                         ["オンライン登録必須", "プロ限定", "ボランティアが完成", "1人1組のみ"]][i],
                     incorrectReasons={str(j): '副詞ではないため。' if i == 0 else '本文の該当記述と一致しません。' for j in range(4) if j != i})
        if created is not None:
            for item in package['passages'] + package['questions']:
                item['createdAt'] = created
        return package

    def test_successful_new_registration(self):
        for slot in ('0700', '1200'):
            with self.subTest(slot=slot):
                package = self.valid_package()
                package['slot'] = slot
                result = import_package(self.base, package)
                self.assertEqual(len(result['questions']), len(self.base['questions']) + 4)
                self.assertEqual(len(result['passages']), len(self.base['passages']) + 1)
                self.assertEqual(result['questions'][-4:], package['questions'])
                self.assertEqual(result['passages'][-1:], package['passages'])
                self.assertEqual(result['selection'], self.base['selection'])
                self.assertEqual(validate(result, baseline=self.base), [])

    def test_past_creation_dates_retained(self):
        today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
        package = self.valid_package(str(today - dt.timedelta(days=30)))
        package['questions'][0]['createdAt'] = '2024-02-29'
        result = import_package(self.base, package)
        self.assertEqual(result['questions'][-4:], package['questions'])
        self.assertEqual(result['passages'][-1:], package['passages'])
        self.assertIn(str(today) + ' JST 0700', result['historyNote'])

    def test_future_creation_dates_rejected(self):
        future = str(dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date() + dt.timedelta(days=1))
        for collection in ('questions', 'passages'):
            with self.subTest(collection=collection):
                package = self.valid_package()
                package[collection][0]['createdAt'] = future
                with self.assertRaisesRegex(ValueError, '未来日'):
                    import_package(self.base, package)

    def test_invalid_creation_dates_rejected(self):
        for collection in ('questions', 'passages'):
            for value in ('2025-02-29', '2026-02-30', '2026-13-01', '2026-1-02', '20261108', '', None, 20261108):
                with self.subTest(collection=collection, value=value):
                    package = self.valid_package()
                    package[collection][0]['createdAt'] = value
                    with self.assertRaisesRegex(ValueError, '有効な日付'):
                        import_package(self.base, package)

    def test_missing_creation_dates_rejected(self):
        for collection in ('questions', 'passages'):
            with self.subTest(collection=collection):
                package = self.valid_package()
                del package[collection][0]['createdAt']
                with self.assertRaisesRegex(ValueError, '有効な日付'):
                    import_package(self.base, package)

    def test_archive_history_and_inputs_unchanged(self):
        today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
        for item in self.base['questions'] + self.base['passages']:
            item['createdAt'] = str(today - dt.timedelta(days=400))
            item['publicationDates'] = [str(today - dt.timedelta(days=200)), str(today)]
            item['publishedAt'] = str(today)
        package = self.valid_package(str(today - dt.timedelta(days=1)))
        # The package fixture inherits publication metadata; new items are unpublished.
        for item in package['questions'] + package['passages']:
            item['publishedAt'] = None
            item['publicationDates'] = []
        before = copy.deepcopy(self.base)
        package_before = copy.deepcopy(package)
        result = import_package(self.base, package, select=True)
        self.assertEqual(result['questions'][:len(before['questions'])], before['questions'])
        self.assertEqual(result['passages'][:len(before['passages'])], before['passages'])
        self.assertEqual(result['selection'], [q['id'] for q in package['questions']])
        self.assertEqual(validate(result, baseline=before), [])
        self.assertEqual(self.base, before)
        self.assertEqual(package, package_before)
        # No nested objects in the returned candidate alias either input.
        result['questions'][0]['publicationDates'].clear()
        result['passages'][0]['publicationDates'].clear()
        result['questions'][-1]['options'][0] = 'changed in candidate only'
        result['passages'][-1]['text'] = 'changed in candidate only'
        self.assertEqual(self.base, before)
        self.assertEqual(package, package_before)

if __name__=='__main__': unittest.main()
