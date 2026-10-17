// ④ 並べ替え: バラバラの句カードを、正しい順にタップしていく。
import { h, phraseEl, resultView } from '../ui/components.js';
import { answer } from '../core/progress.js';
import { shuffle } from '../core/util.js';

export const meta = { key: 'order', title: '並べ替え', desc: 'バラバラの句を正しい順にタップ。流れをつかむ' };

const WINDOW = 8;

export function mount(root, { stage, phrases, retry, backHref }) {
  const start = phrases.length > WINDOW ? Math.floor(Math.random() * (phrases.length - WINDOW + 1)) : 0;
  const seq = phrases.slice(start, start + WINDOW);
  let cards = shuffle(seq);
  while (seq.length > 1 && cards.every((c, i) => c.kanji === seq[i].kanji)) cards = shuffle(seq);

  const misses = new Array(seq.length).fill(0);
  const hinted = new Array(seq.length).fill(false);
  let pos = 0;
  const t0 = Date.now();

  const slots = h('ol', { class: 'slots' }, seq.map(() => h('li', { class: 'slot' }, '・・・')));
  const pool = h('div', { class: 'pool' });
  const hintBtn = h('button', { class: 'btn ghost', onclick: hint }, 'ヒント（頭の一字）');
  const box = h('section', { class: 'quiz' },
    h('p', { class: 'muted small' }, `${seq[0].id}句目から${seq.at(-1).id}句目までを順番に`),
    slots, pool, h('div', { class: 'q-actions' }, hintBtn));
  root.append(box);

  cards.forEach((p) => {
    const btn = h('button', { class: 'card-ku', onclick: () => tap(p, btn) }, phraseEl(p));
    pool.append(btn);
  });
  slots.children[0].classList.add('next');

  function hint() {
    hinted[pos] = true;
    slots.children[pos].textContent = `${seq[pos].kanji[0]}・・・`;
  }

  function tap(p, btn) {
    if (p.kanji !== seq[pos].kanji) {
      misses[pos]++;
      btn.classList.remove('shake');
      void btn.offsetWidth;
      btn.classList.add('shake');
      return;
    }
    const grade = misses[pos] === 0 && !hinted[pos] ? 'good' : misses[pos] <= 1 ? 'fair' : 'bad';
    answer(seq[pos].id, grade);
    const slot = slots.children[pos];
    slot.replaceChildren(phraseEl(seq[pos]));
    slot.className = `slot placed ${grade}`;
    btn.remove();
    pos++;
    if (pos < seq.length) { slots.children[pos].classList.add('next'); return; }
    const sec = Math.round((Date.now() - t0) / 1000);
    const perfect = misses.filter((m, i) => m === 0 && !hinted[i]).length;
    box.append(resultView({ score: perfect, total: seq.length, stage, retry, backHref,
      lines: [`かかった時間 ${sec} 秒・まちがい ${misses.reduce((a, b) => a + b, 0)} 回`] }));
    hintBtn.remove();
  }
}
