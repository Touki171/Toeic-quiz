"""Fail-closed registry validation. Standard library only; dates use Asia/Tokyo."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def normalize(text):
    return re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', text).casefold()).strip()

def content(item):
    if 'text' in item:
        return item['text']
    return item['prompt'] + '\n' + '\n'.join(sorted(item['options']))

def fingerprint(item):
    return hashlib.sha256(normalize(content(item)).encode()).hexdigest()

def day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('日付は YYYY-MM-DD が必要です')
    return dt.date.fromisoformat(value)

def validate(data, release=None, baseline=None):
    errors = []
    def require(ok, message):
        if not ok:
            errors.append(message)
    require(data.get('schemaVersion') == 1, 'schemaVersion が不正です')
    require(data.get('historyComplete') is True, '履歴が不完全です')
    require(bool(data.get('historyNote', '').strip()), '履歴確認メモが必要です')
    for key in ('questions', 'passages', 'selection', 'similarityReviews'):
        require(isinstance(data.get(key), list), key + ' は配列が必要です')
    if errors:
        return errors
    questions, passages = data['questions'], data['passages']
    all_items = questions + passages
    ids = [x.get('id') for x in all_items]
    require(all(isinstance(x, str) and x.strip() for x in ids), '全項目に ID が必要です')
    require(len(ids) == len(set(ids)), 'ID が重複しています')
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    release_day = day(release) if release else None
    require(not release_day or release_day == today, '公開日は実行当日（日本時間）が必要です')
    for item in all_items:
        label = str(item.get('id'))
        try:
            created = day(item['createdAt'])
            require(created <= today, label + ': 作成日が未来です')
            dates = item['publicationDates']
            require(isinstance(dates, list), label + ': 公開履歴が必要です')
            parsed = [day(x) for x in dates]
            require(parsed == sorted(set(parsed)), label + ': 公開履歴は重複なしの昇順が必要です')
            require(all(created <= x <= today for x in parsed), label + ': 公開日が範囲外です')
            require(item['publishedAt'] == (dates[-1] if dates else None), label + ': 最終公開日と履歴が不一致です')
            require(all((b-a).days >= 183 for a,b in zip(parsed, parsed[1:])), label + ': 再利用間隔が183日未満です')
        except (KeyError, TypeError, ValueError):
            errors.append(label + ': 作成日・公開日・公開履歴が欠損または不正です')
        require(isinstance(item.get('translation'), str) and bool(item['translation'].strip()), label + ': 日本語訳が必要です')
    passage_ids = {p.get('id') for p in passages}
    for p in passages:
        require(isinstance(p.get('text'), str) and 180 <= len(p['text'].split()) <= 250, str(p.get('id')) + ': 長文は180〜250語が必要です（空白区切り）')
        require(bool(p.get('title')), '長文タイトルが必要です')
    for q in questions:
        label = str(q.get('id'))
        require(q.get('part') in (5, 7), label + ': Part が不正です')
        require((q.get('passageId') in passage_ids) if q.get('part') == 7 else q.get('passageId') is None, label + ': 長文参照が不正です')
        require(isinstance(q.get('prompt'), str) and bool(q['prompt'].strip()), label + ': 問題文が必要です')
        opts = q.get('options')
        require(isinstance(opts, list) and len(opts) == 4 and all(isinstance(x,str) and x.strip() for x in opts) and len({normalize(x) for x in opts}) == 4, label + ': 異なる4択が必要です')
        answer = q.get('answer')
        require(type(answer) is int and answer in range(4), label + ': 正解が不正です')
        require(bool(q.get('evidence')), label + ': 根拠が必要です')
        reasons = q.get('incorrectReasons', {})
        require(isinstance(reasons, dict) and set(reasons) == {str(i) for i in range(4) if i != answer} and all(isinstance(x,str) and x.strip() for x in reasons.values()), label + ': 誤答3つの理由が必要です')
        require(isinstance(q.get('optionTranslations'), list) and len(q['optionTranslations']) == 4 and all(q['optionTranslations']), label + ': 選択肢の訳が必要です')
    selection = data['selection']
    selected = [q for q in questions if q.get('id') in selection]
    require(len(selection) == 4 and len(set(selection)) == 4 and len(selected) == 4, '選択問題は有効な異なる4問が必要です')
    require(sum(q.get('part') == 5 for q in selected) == 1 and sum(q.get('part') == 7 for q in selected) == 3, 'Part 5 は1問、Part 7 は3問が必要です')
    require(len({q.get('passageId') for q in selected if q.get('part') == 7}) == 1, 'Part 7 は同じ長文を参照してください')
    if errors:
        return errors
    # Compare the whole retained archive, including unselected questions and passages.
    for group in (questions, passages):
        for i,a in enumerate(group):
            for b in group[i+1:]:
                x,y = normalize(content(a)), normalize(content(b))
                # Identical stems are also forbidden, even if distractors differ.
                exact = x == y or ('prompt' in a and normalize(a['prompt']) == normalize(b['prompt']))
                pair = sorted([a['id'], b['id']])
                require(not exact, '完全一致は禁止: ' + ', '.join(pair))
                tokens_a, tokens_b = set(x.split()), set(y.split())
                similarity = max(difflib.SequenceMatcher(None,x,y).ratio(), len(tokens_a & tokens_b)/max(1,len(tokens_a | tokens_b)))
                if not exact and similarity >= .72:
                    reviewed = any(r.get('ids') == pair and r.get('fingerprints') == {a['id']:fingerprint(a),b['id']:fingerprint(b)} and str(r.get('reviewer','')).strip() and str(r.get('reason','')).strip() and _valid_review_date(r.get('reviewedAt'),today) for r in data['similarityReviews'] if isinstance(r,dict))
                    require(reviewed, f'類似問題は要確認 ({similarity:.2f}): {pair}; fingerprints=' + str({a["id"]:fingerprint(a),b["id"]:fingerprint(b)}))
    if baseline:
        old = {x['id']: x for x in baseline['questions'] + baseline['passages']}
        current = {x['id']:x for x in all_items}
        for id,item in old.items():
            require(id in current, id + ': 履歴項目を削除できません')
            if id in current:
                require(content(item) == content(current[id]) and item.get('answer') == current[id].get('answer') and item.get('passageId') == current[id].get('passageId') and item['createdAt'] == current[id]['createdAt'], id + ': 既存問題の本文・正解・参照・作成日は変更できません。新IDで追加してください')
                dates = current[id]['publicationDates']
                require(dates[:len(item['publicationDates'])] == item['publicationDates'], id + ': 公開履歴は追記のみです')
    if release_day:
        targets = selected + [p for p in passages if p['id'] in {q['passageId'] for q in selected}]
        for item in targets:
            require(item['publishedAt'] == release, item['id'] + ': 公開用ビルドには当日の公開履歴が必要です')
    return errors

def _valid_review_date(value,today):
    try:
        return day(value) <= today
    except (ValueError,TypeError):
        return False

def load(path):
    return json.loads(Path(path).read_text())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--registry', default=str(ROOT/'question-registry.json'))
    parser.add_argument('--baseline')
    parser.add_argument('--release', help='YYYY-MM-DD; require publication records for this release')
    args = parser.parse_args()
    try:
        errors = validate(load(args.registry),args.release,load(args.baseline) if args.baseline else None)
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
        errors = ['台帳を検証できません: ' + str(exc)]
    if errors:
        print('\n'.join('ERROR: '+x for x in errors))
        return 1
    print('Registry OK: 完全一致なし・未承認の類似なし・履歴整合')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
