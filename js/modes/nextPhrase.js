// ③ 次の句は？: 直前の句を見て、続く句を4択で選ぶ。
import { h, phraseEl, resultView } from '../ui/components.js';
import { pickWeighted } from '../core/srs.js';
import { answer } from '../core/progress.js';
import { shuffle, uniqueByKanji } from '../core/util.js';
import { SUTRA } from '../data/sekai-ge.js';

export const meta = { key: 'next', title: '次の句は？', desc: '前の句から続きを4択で選ぶ。順番の記憶に' };

export function mount(root, { stage, phrases, retry, backHref }) {
  const all = SUTRA.phrases;
  // 次の句が同じ段の中にあるものだけ出題（重みは「答えになる句」の記憶度）
  const candidates = phrases.filter((p) => p.id < stage.to);
  const questions = pickWeighted(candidates, Math.min(8, candidates.length), (p) => p.id + 1);
  const box = h('section', { class: 'quiz' });
  root.append(box);
  let qi = 0;
  let correct = 0;
  let alive = true;

  function next() {
    if (qi >= questions.length) {
      box.replaceChildren(resultView({ score: correct, total: questions.length, stage, retry, backHref }));
      return;
    }
    const cur = questions[qi];
    const target = all[cur.id]; // id は1始まりなので all[cur.id] が次の句
    const prev = all[cur.id - 2];
    const exclude = new Set([target.kanji, cur.kanji]);
    let pool = uniqueByKanji(phrases).filter((p) => !exclude.has(p.kanji));
    if (pool.length < 3) pool = uniqueByKanji(all).filter((p) => !exclude.has(p.kanji));
    const options = shuffle([target, ...shuffle(pool).slice(0, 3)]);

    const list = h('div', { class: 'choices' }, options.map((o) =>
      h('button', { class: 'choice', onclick: (e) => choose(o, e.currentTarget) }, phraseEl(o))));

    box.replaceChildren(
      h('p', { class: 'q-count' }, `${qi + 1} / ${questions.length}`),
      h('p', { class: 'q-context' }, prev ? prev.kanji : '（はじまり）'),
      h('div', { class: 'q-phrase' }, phraseEl(cur), h('span', { class: 'q-arrow' }, '…次は？')),
      list);

    function choose(o, btn) {
      list.querySelectorAll('button').forEach((b) => { b.disabled = true; });
      const ok = o.kanji === target.kanji;
      btn.classList.add(ok ? 'right' : 'wrong');
      if (!ok) list.children[options.indexOf(target)].classList.add('right');
      if (ok) correct++;
      answer(target.id, ok ? 'good' : 'bad');
      setTimeout(() => { if (alive) { qi++; next(); } }, ok ? 800 : 1600);
    }
  }

  next();
  return () => { alive = false; };
}
