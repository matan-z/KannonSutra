// ② 穴埋め: 伏せた字を候補から選ぶ。覚えている句ほど伏せ字が増える。
import { h, phraseEl, resultView } from '../ui/components.js';
import { pickWeighted, boxOf } from '../core/srs.js';
import { answer } from '../core/progress.js';
import { shuffle } from '../core/util.js';
import { SUTRA } from '../data/sekai-ge.js';

export const meta = { key: 'fill', title: '穴埋め', desc: '□ に入る字を選ぶ。覚えるほど □ が増える' };

const FEEDBACK = { good: '善哉！', fair: 'おしい', bad: 'もう一度おさらい' };

export function mount(root, { stage, phrases, retry, backHref }) {
  const questions = pickWeighted(phrases, Math.min(phrases.length, 10));
  const allChars = [...new Set(SUTRA.phrases.flatMap((p) => [...p.kanji]))];
  const stageChars = [...new Set(phrases.flatMap((p) => [...p.kanji]))];
  const box = h('section', { class: 'quiz' });
  root.append(box);
  let qi = 0;
  let correct = 0;
  let alive = true;

  function next() {
    if (qi >= questions.length) {
      box.replaceChildren(resultView({ score: correct, total: questions.length, stage, retry, backHref,
        lines: ['ノーミス・ヒントなしで正解した句の数です'] }));
      return;
    }
    const p = questions[qi];
    const chars = [...p.kanji];
    const b = boxOf(p.id);
    const k = b < 2 ? 1 : b < 4 ? 2 : 3;
    const blanks = shuffle(chars.map((_, i) => i)).slice(0, k).sort((x, y) => x - y);
    const node = phraseEl(p, { hidden: new Set(blanks) });
    const prev = SUTRA.phrases[p.id - 2];
    const tiles = h('div', { class: 'tiles' });
    let step = 0;
    let mistakes = 0;
    let hinted = false;
    const jiAt = (i) => node.querySelector(`[data-i="${i}"]`);

    box.replaceChildren(
      h('p', { class: 'q-count' }, `${qi + 1} / ${questions.length}`),
      h('p', { class: 'q-context' }, prev ? prev.kanji : '（はじまり）'),
      h('div', { class: 'q-phrase' }, node),
      tiles,
      h('div', { class: 'q-actions' }, h('button', {
        class: 'btn ghost',
        onclick: () => { hinted = true; jiAt(blanks[step])?.classList.add('hint'); },
      }, 'ヒント（読み）')));

    function renderTiles() {
      const ans = chars[blanks[step]];
      node.querySelectorAll('.ji').forEach((el) => el.classList.remove('current'));
      jiAt(blanks[step]).classList.add('current');
      const pool = (stageChars.length > 6 ? stageChars : allChars).filter((c) => c !== ans);
      tiles.replaceChildren(...shuffle([ans, ...shuffle(pool).slice(0, 5)]).map((c) =>
        h('button', { class: 'tile', onclick: (e) => pick(c, e.currentTarget) }, c)));
    }

    function pick(c, btn) {
      const idx = blanks[step];
      if (c !== chars[idx]) {
        mistakes++;
        btn.disabled = true;
        btn.classList.add('wrong');
        return;
      }
      const ji = jiAt(idx);
      ji.classList.remove('blank', 'current', 'hint');
      ji.classList.add('filled');
      ji.querySelector('.rb').textContent = c;
      step++;
      if (step < blanks.length) { renderTiles(); return; }
      const grade = mistakes === 0 && !hinted ? 'good' : mistakes <= 1 ? 'fair' : 'bad';
      if (grade === 'good') correct++;
      answer(p.id, grade);
      tiles.replaceChildren(h('p', { class: `q-feedback ${grade}` }, FEEDBACK[grade]));
      setTimeout(() => { if (alive) { qi++; next(); } }, 900);
    }

    renderTiles();
  }

  next();
  return () => { alive = false; };
}
