"""Generate static HTML only after a complete registry and history check."""
import argparse
import html
import shutil
import subprocess
from pathlib import Path
from registry import ROOT, load, validate

OUT = ROOT/'dist'
def esc(value):
    return html.escape(str(value), quote=True)

def question(q,number):
    id=q['id']; correct=q['answer']; letters='ABCD'
    options=''.join(f'<label class="choice" for="{id}-{i}"><input id="{id}-{i}" type="radio" name="{id}" value="{i}" aria-controls="{id}-explanation"><span class="letter">{letters[i]}</span><span lang="en">{esc(option)}</span></label>' for i,option in enumerate(q['options']))
    outcomes=''.join(f'<p class="outcome outcome-{i}" role="status">{"✓ 正解です" if i == correct else "不正解です。根拠を確認しましょう"} <span>あなたの回答：{letters[i]}</span></p>' for i in range(4))
    reasons=''.join(f'<li><strong>{letters[i]}：{esc(q["options"][i])}</strong><br>{esc(q["incorrectReasons"][str(i)])}</li>' for i in range(4) if i != correct)
    translations=''.join(f'<li>{letters[i]}：{esc(t)}</li>' for i,t in enumerate(q['optionTranslations']))
    return f'''<fieldset class="question" id="{id}"><legend><span class="eyebrow">QUESTION {number:02d}</span><span class="prompt" lang="en">{esc(q['prompt'])}</span></legend><div class="choices">{options}</div>
<div class="explanation" id="{id}-explanation">{outcomes}<p class="answer">正解：{letters[correct]} <span lang="en">{esc(q['options'][correct])}</span></p><h3>日本語訳</h3><p>{esc(q['translation'])}</p><ul class="translations">{translations}</ul><h3>正解の根拠</h3><p>{esc(q['evidence'])}</p><h3>ほかの選択肢が不適切な理由</h3><ul class="reasons">{reasons}</ul></div></fieldset>'''

def generate(data,preview):
    qs={q['id']:q for q in data['questions']}; selected=[qs[id] for id in data['selection']]
    passage=next(p for p in data['passages'] if p['id']==next(q['passageId'] for q in selected if q['part']==7))
    passage_html=''.join(f'<p>{esc(p)}</p>' for p in passage['text'].split('\n\n'))
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="オリジナル問題で学ぶ非公式TOEIC学習教材。Part 5とPart 7を、訳と根拠で理解する。"><meta name="color-scheme" content="light"><title>TOEIC Study Notes | 今日の4問</title><link rel="stylesheet" href="styles.css"></head>
<body><a class="skip" href="#main">問題へ進む</a><header class="topbar"><a class="brand" href="#">Study<span>Notes</span><small>ENGLISH PRACTICE</small></a><span class="edition">TOEIC 学習ノート</span></header>
<main id="main"><section class="hero"><p class="eyebrow">A LITTLE PRACTICE, EVERY DAY.</p><h1>読む。選ぶ。<br><span>理由まで、わかる。</span></h1><p class="intro">短い一問と、ひとつの長文。<br>正解の先にある「なぜ」を学びましょう。</p><div class="pills"><span>Part 5 · 1問</span><span>Part 7 · 3問</span><span>目安 8分</span></div></section>
{'<p class="draft">レビュー用プレビュー · 未公開の教材です</p>' if preview else ''}
<nav class="section-nav" aria-label="パートを選ぶ"><a href="#part5">01 <strong>文法・語彙</strong><span>Part 5 ↗</span></a><a href="#part7">02 <strong>読解</strong><span>Part 7 ↗</span></a></nav>
<p class="instruction">選択肢をタップすると、すぐ下に正誤と解説が表示されます。回答は何度でも変更できます。</p><noscript><p class="notice">JavaScript は不要です。選択肢を選ぶと CSS で解説を表示します。</p></noscript><p class="compat">解説の自動表示には Safari 15.4 以降など、CSS :has() 対応ブラウザーを使用してください。</p>
<section id="part5" class="part"><div class="section-heading"><div><p class="eyebrow">01 / SHORT PRACTICE</p><h2>文法・語彙 <span>Part 5</span></h2></div><span class="count">1 QUESTION</span></div>{''.join(question(q,1) for q in selected if q['part']==5)}</section>
<section id="part7" class="part"><div class="section-heading"><div><p class="eyebrow">02 / READ & UNDERSTAND</p><h2>読解 <span>Part 7</span></h2></div><span class="count">3 QUESTIONS</span></div><article class="passage"><div class="passage-meta">EMAIL <span>{len(passage['text'].split())} WORDS</span></div><h3 lang="en">{esc(passage['title'])}</h3><div class="english" lang="en">{passage_html}</div><details class="passage-translation"><summary>長文の日本語訳を読む</summary><p>{esc(passage['translation'])}</p></details></article>{''.join(question(q,i+2) for i,q in enumerate(q for q in selected if q['part']==7))}</section>
<aside class="finish"><span>✦</span><h2>今日の一歩を、明日の力に。</h2><p>迷った選択肢の理由を、もう一度読んでみましょう。</p><a href="#part5">最初の問題へ戻る ↑</a></aside></main>
<footer><a class="brand" href="#">Study<span>Notes</span></a><p>本サイトは独自に作成したオリジナル問題を収録する非公式教材です。<br>ETS の承認・推奨・提携を受けたものではありません。<br>TOEIC は ETS の登録商標です。</p><p class="fine">学習状況や回答は送信・保存しません。ページを再読込すると回答がリセットされます。</p></footer></body></html>'''

def baseline():
    # Compare with the actual target branch. Missing Git/base is an error, not a bypass.
    files=subprocess.check_output(['git','ls-tree','-r','--name-only','origin/main'],cwd=ROOT,text=True).splitlines()
    if 'question-registry.json' not in files:
        if files != ['README.md']:
            raise ValueError('基準ブランチに台帳がなく、初期READMEのみでもありません。履歴を復元してください')
        return None
    import json
    previous = json.loads(subprocess.check_output(['git','show','origin/main:question-registry.json'],cwd=ROOT,text=True))
    issues = validate(previous)
    if issues:
        raise ValueError('基準台帳が不完全です: ' + '; '.join(issues))
    return previous

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--release',help='公開当日の YYYY-MM-DD。省略時は未公開プレビュー')
    args=parser.parse_args()
    # Remove stale artifacts before any validation; failed builds leave nothing deployable.
    shutil.rmtree(OUT,ignore_errors=True)
    try:
        data=load(ROOT/'question-registry.json')
        errors=validate(data,args.release,baseline())
        if errors:
            raise ValueError('\n'.join(errors))
        OUT.mkdir()
        (OUT/'index.html').write_text(generate(data,not args.release))
        shutil.copy(ROOT/'styles.css',OUT/'styles.css')
    except (OSError,ValueError,TypeError,KeyError,AttributeError,subprocess.CalledProcessError) as exc:
        shutil.rmtree(OUT,ignore_errors=True)
        print('BUILD BLOCKED:',exc)
        return 1
    print('Built dist/ ('+('release' if args.release else 'unpublished preview')+')')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
