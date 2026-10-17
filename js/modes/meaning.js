// ⑤ 意味あわせ: 句 → 現代語訳、現代語訳 → 句 を交互に4択で答える。意味の記憶度に記録。
import { h, phraseEl, resultView } from '../ui/components.js';
import { pickWeighted, meaningKey } from '../core/srs.js';
import { answer } from '../core/progress.js';
import { shuffle, uniqueByKanji } from '../core/util.js';
import { SUTRA } from '../data/sekai-ge.js';

export const meta = { key: 'meaning', title: '意味あわせ', desc: '句と現代語訳を結びつける。お経の意味がわかる' };

export function mount(root, { stage, phrases, retry, backHref }) {
  // 繰り返し句（念彼観音力）は1問にまとめる
  const pool = uniqueByKanji(phrases);
  const questions = pickWeighted(pool, Math.min(8, pool.length), (p) => meaningKey(p.id));
  const box = h('section', { class: 'quiz' });
  root.append(box);
  let qi = 0;
  let correct = 0;
  let alive = true;

  function next() {
    if (qi >= questions.length) {
      box.replaceChildren(resultView({ score: correct, total: questions.length, stage, retry, backHref,
        lines: ['意味の記憶度は、段の画面の「意味」で確かめられます'] }));
      return;
    }
    const target = questions[qi];
    const toMeaning = qi % 2 === 0; // 偶数問: 句→訳、奇数問: 訳→句
    let others = pool.filter((p) => p.kanji !== target.kanji);
    if (others.length < 3) others = uniqueByKanji(SUTRA.phrases).filter((p) => p.kanji !== target.kanji);
    const options = shuffle([target, ...shuffle(others).slice(0, 3)]);

    const list = h('div', { class: `choices${toMeaning ? ' choices-meaning' : ''}` }, options.map((o) =>
      h('button', { class: 'choice', onclick: (e) => choose(o, e.currentTarget) },
        toMeaning ? o.meaning : phraseEl(o))));

    box.replaceChildren(
      h('p', { class: 'q-count' }, `${qi + 1} / ${questions.length}`),
      h('p', { class: 'muted small' }, toMeaning ? 'この句の意味は？' : 'この意味の句は？'),
      toMeaning
        ? h('div', { class: 'q-phrase' }, phraseEl(target))
        : h('p', { class: 'q-meaning' }, target.meaning),
      list);

    function choose(o, btn) {
      list.querySelectorAll('button').forEach((b) => { b.disabled = true; });
      const ok = o.kanji === target.kanji;
      btn.classList.add(ok ? 'right' : 'wrong');
      if (!ok) list.children[options.indexOf(target)].classList.add('right');
      if (ok) correct++;
      answer(target.id, ok ? 'good' : 'bad', 'meaning');
      setTimeout(() => { if (alive) { qi++; next(); } }, ok ? 900 : 1800);
    }
  }

  next();
  return () => { alive = false; };
}
