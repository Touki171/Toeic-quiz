"""Import a ChatGPT-generated daily JSON package without publishing it.

Usage: python3 scripts/import_daily.py daily.json --output updated-registry.json
"""
import argparse
import copy
import datetime as dt
import json
from pathlib import Path

from registry import day, validate

ROOT = Path(__file__).resolve().parents[1]


def import_package(registry, package, *, select=False):
    if not isinstance(package, dict) or set(package) != {'slot', 'passages', 'questions'}:
        raise ValueError('入力は slot, passages, questions の3項目のみ必要です')
    slot = package['slot']
    if slot not in ('0700', '1200'):
        raise ValueError('slot は 0700 または 1200 にしてください')
    passages, questions = package['passages'], package['questions']
    if not isinstance(passages, list) or len(passages) != 1 or not isinstance(questions, list) or len(questions) != 4:
        raise ValueError('長文1件、問題4件（Part 5が1件、Part 7が3件）が必要です')
    if sum(q.get('part') == 5 for q in questions) != 1 or sum(q.get('part') == 7 for q in questions) != 3:
        raise ValueError('Part 5が1件、Part 7が3件必要です')
    passage_id = passages[0].get('id')
    if any(q.get('passageId') != passage_id for q in questions if q.get('part') == 7):
        raise ValueError('Part 7のpassageIdが一致しません')
    if any(q.get('passageId') is not None for q in questions if q.get('part') == 5):
        raise ValueError('Part 5のpassageIdはnullが必要です')
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    date = today.isoformat()
    for item in passages + questions:
        try:
            created = day(item.get('createdAt'))
        except (TypeError, ValueError):
            raise ValueError('createdAtは有効な日付（YYYY-MM-DD）が必要です') from None
        if created > today:
            raise ValueError('createdAtに未来日は指定できません（登録日以前が必要です）: ' + date)
        if item.get('publishedAt', 'missing') is not None or item.get('publicationDates') != []:
            raise ValueError('未公開問題には publishedAt:null と publicationDates:[] が必要です')
    result = copy.deepcopy(registry)
    existing_ids = {x['id'] for x in result['questions'] + result['passages']}
    new_ids = [x.get('id') for x in passages + questions]
    if any(not isinstance(x, str) or not x.strip() for x in new_ids) or len(new_ids) != len(set(new_ids)) or existing_ids.intersection(new_ids):
        raise ValueError('IDが空欄・重複・既存台帳と衝突しています')
    result['passages'].extend(copy.deepcopy(passages))
    result['questions'].extend(copy.deepcopy(questions))
    if select:
        result['selection'] = [q['id'] for q in questions]
    result['historyNote'] = result['historyNote'].rstrip() + f'\n{date} JST {slot}: 4問と長文1件を未公開で登録。過去の公開履歴は維持。'
    errors = validate(result, baseline=registry)
    if errors:
        raise ValueError('台帳検査に失敗しました:\n- ' + '\n- '.join(errors))
    return result


def main():
    parser = argparse.ArgumentParser(description='ChatGPT問題JSONを未公開で共通台帳に追記')
    parser.add_argument('package', type=Path)
    parser.add_argument('--registry', type=Path, default=ROOT / 'question-registry.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'question-registry.updated.json')
    parser.add_argument('--select', action='store_true', help='今回の4問をプレビュー対象にする（公開はしない）')
    args = parser.parse_args()
    if args.output.resolve() == args.registry.resolve() or args.output.exists():
        parser.error('既存ファイルの上書きは禁止です。未使用の --output を指定してください')
    try:
        original = json.loads(args.registry.read_text(encoding='utf-8'))
        package = json.loads(args.package.read_text(encoding='utf-8'))
        result = import_package(original, package, select=args.select)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        parser.error(str(e))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'登録案を作成しました（未公開）: {args.output}')
    print('内容をレビュー後、question-registry.jsonに反映してCIで再検査してください。')

if __name__ == '__main__':
    main()
