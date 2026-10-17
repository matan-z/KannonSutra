// ⑤ ひとり読経: 句を伏せたまま声に出して読み、答え合わせして自己採点する。
import { h, phraseEl, sutraText, meaningEl, resultView } from '../ui/components.js';
import { answer } from '../core/progress.js';

export const meta = { key: 'chant', title: 'ひとり読経', desc: '経本を見ずに声に出して読み、自分で答え合わせ' };

const LABEL = { good: '覚えていた', fair: 'あやしい', bad: '忘れた' };

export function mount(root, { stage, phrases, retry, backHref }) {
  const slots = phrases.map((p) => phraseEl(p, { hidden: new Set([...p.kanji].keys()), cls: 'masked' }));
  const text = sutraText(slots, { withTitle: phrases[0].id === 1 });
  const prompt = h('p', { class: 'chant-prompt', 'aria-live': 'polite' });
  const meaningBox = h('div', { class: 'chant-meaning' });
  const actions = h('div', { class: 'q-actions chant-actions' });
  const tally = { good: 0, fair: 0, bad: 0 };
  let i = 0;
  let revealed = false;
  let hinted = false;

  root.append(
    h('p', { class: 'muted small' }, '伏せられた句を声に出して読んでから「答えを見る」。キーボード: Space で答え、1・2・3 で採点'),
    text, prompt, meaningBox, actions);

  function show() {
    if (i >= phrases.length) {
      actions.replaceChildren();
      meaningBox.replaceChildren();
      prompt.textContent = '';
      root.append(resultView({ score: tally.good, total: phrases.length, stage, retry, backHref,
        title: 'おつとめ完了',
        lines: [`覚えていた ${tally.good}・あやしい ${tally.fair}・忘れた ${tally.bad}`] }));
      return;
    }
    revealed = false;
    hinted = false;
    slots.forEach((s, j) => s.classList.toggle('current', j === i));
    slots[i].scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
    prompt.textContent = `${phrases[i].id}句目を読んでください`;
    meaningBox.replaceChildren();
    actions.replaceChildren(
      h('button', { class: 'btn ghost', onclick: hint }, '頭の一字'),
      h('button', { class: 'btn primary', onclick: reveal }, '答えを見る'));
  }

  function hint() {
    hinted = true;
    const first = slots[i].querySelector('.ji');
    first.classList.remove('blank');
    first.querySelector('.rb').textContent = phrases[i].kanji[0];
  }

  function reveal() {
    revealed = true;
    const shown = phraseEl(phrases[i], { cls: 'revealed current' });
    slots[i].replaceWith(shown);
    slots[i] = shown;
    prompt.textContent = 'どうでしたか？';
    meaningBox.replaceChildren(meaningEl(phrases[i], 'opt'));
    actions.replaceChildren(...['good', 'fair', 'bad'].map((g) =>
      h('button', { class: `btn rate ${g}`, disabled: g === 'good' && hinted, onclick: () => rate(g) }, LABEL[g])));
  }

  function rate(g) {
    tally[g]++;
    slots[i].classList.add(`rated-${g}`);
    answer(phrases[i].id, g);
    i++;
    show();
  }

  const onKey = (e) => {
    if (i >= phrases.length || (e.target instanceof Element && e.target.closest('input, button'))) return;
    if (!revealed && e.code === 'Space') { e.preventDefault(); reveal(); }
    else if (revealed && ['1', '2', '3'].includes(e.key)) {
      const g = ['good', 'fair', 'bad'][Number(e.key) - 1];
      if (!(g === 'good' && hinted)) rate(g);
    }
  };
  addEventListener('keydown', onKey);
  show();
  return () => removeEventListener('keydown', onKey);
}
