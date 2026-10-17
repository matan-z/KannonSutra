import { isCleared } from '../core/progress.js';
import { boxOf, MAX_BOX } from '../core/srs.js';
import { store } from '../core/store.js';
import { SUTRA_TITLE } from '../data/sekai-ge.js';

// h('div', { class: 'x', onclick }, ...children)
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props ?? {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : String(c));
  }
  return el;
}

// 1句をルビ付きで表示。hidden に入れた字は伏せ字（□）になる。
export function phraseEl(phrase, { hidden = new Set(), cls = '' } = {}) {
  return h('span', { class: `ku ${cls}`.trim(), 'data-id': phrase.id },
    [...phrase.kanji].map((ch, i) => h('ruby', { class: hidden.has(i) ? 'ji blank' : 'ji', 'data-i': i },
      h('span', { class: 'rb' }, hidden.has(i) ? '　' : ch),
      h('rt', {}, phrase.yomi[i]))));
}

// 現代語訳の1行
export const meaningEl = (phrase, cls = '') => h('p', { class: `meaning ${cls}`.trim() }, phrase.meaning);

// 経本の体裁: 1行（縦書きなら1列）に2句、1偈（4句）ごとに少し間をあける
// withTitle: 第一段・通し読経では、先頭に経題を1行（縦書きなら1列）置く
export function sutraText(kuEls, { withTitle = false } = {}) {
  const lines = withTitle ? [kyodaiEl()] : [];
  for (let i = 0; i < kuEls.length; i += 2) {
    lines.push(h('div', { class: `gyo${(i / 2) % 2 === 1 ? ' verse-end' : ''}` }, kuEls.slice(i, i + 2)));
  }
  return h('div', { class: 'sutra-text', tabindex: 0 }, lines);
}

// 経題（ルビ付き）。.ji を付けないので経本の強調・タップ対象にならない
export function kyodaiEl() {
  return h('div', { class: 'gyo kyodai', 'aria-label': `経題 ${SUTRA_TITLE.kanji}` },
    h('span', { class: 'ku' }, [...SUTRA_TITLE.kanji].map((ch, i) =>
      h('ruby', {}, h('span', { class: 'rb' }, ch), h('rt', {}, SUTRA_TITLE.yomi[i])))));
}

// 記憶度を ● の数で表示
export function masteryDots(id, label = '記憶度') {
  const box = boxOf(id);
  return h('span', { class: 'dots', title: label, 'aria-label': `${label} ${box} / ${MAX_BOX}` },
    Array.from({ length: MAX_BOX }, (_, i) => h('i', { class: i < box ? 'on' : '' })));
}

export function meter(ratio, label) {
  return h('div', { class: 'meter', role: 'progressbar', 'aria-valuenow': Math.round(ratio * 100),
    'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-label': label },
  h('span', { style: `width:${ratio * 100}%` }));
}

export function topBar(title, backHref, sub) {
  const merit = h('span', { class: 'merit' }, `功徳 ${store.get().stats.merit}`);
  const bar = h('header', { class: 'topbar' },
    h('a', { class: 'back', href: backHref }, '‹ 戻る'),
    h('div', { class: 'topbar-title' }, h('strong', {}, title), sub ? h('small', {}, sub) : null),
    merit);
  const off = store.subscribe((s) => { merit.textContent = `功徳 ${s.stats.merit}`; });
  return { el: bar, off };
}

export function resultView({ title = 'おつとめ完了', score, total, lines = [], stage, retry, backHref }) {
  const cleared = stage && stage.id !== 'all' && isCleared(stage);
  return h('section', { class: 'card result' },
    h('p', { class: 'eyebrow' }, '結果'),
    h('h2', {}, title),
    score != null ? h('p', { class: 'result-score' }, h('strong', {}, score), ` / ${total}`) : null,
    lines.map((l) => h('p', { class: 'muted' }, l)),
    cleared ? h('p', { class: 'badge-clear' }, `${stage.title} 成就`) : null,
    h('div', { class: 'row' },
      h('button', { class: 'btn primary', onclick: retry }, 'もう一度'),
      h('a', { class: 'btn', href: backHref }, '段に戻る')));
}
