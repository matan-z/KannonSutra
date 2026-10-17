import { h, meter, masteryDots, meaningEl, topBar } from '../components.js';
import { getStage, stagePhrases, stageMastery, stageMeaningMastery, isUnlocked } from '../../core/progress.js';
import { meaningKey } from '../../core/srs.js';
import { SUTRA_TITLE } from '../../data/sekai-ge.js';
import { MODES } from '../../modes/index.js';
import { go } from '../../router.js';

export function stageScreen(root, { id }) {
  const stage = getStage(id);
  if (!stage) { go('/'); return null; }
  const open = isUnlocked(stage);
  const phrases = stagePhrases(stage);
  const bar = topBar(stage.title, '#/', stage.name);

  root.append(bar.el, h('main', { class: 'stage' },
    h('section', { class: 'card' },
      h('p', { class: 'eyebrow' }, `${stage.from}〜${stage.to}句`),
      h('h2', {}, `${stage.title}「${stage.name}」`),
      h('p', { class: 'meter-label' }, '読み'), meter(stageMastery(stage), '読みの記憶度'),
      h('p', { class: 'meter-label' }, '意味'), meter(stageMeaningMastery(stage), '意味の記憶度'),
      stage.from === 1 ? h('p', { class: 'kyodai-line' },
        h('span', { class: 'pl-kanji' }, SUTRA_TITLE.kanji),
        h('span', { class: 'pl-yomi' }, SUTRA_TITLE.yomi.join('')),
        h('small', { class: 'muted' }, '（経題・最初に読む）')) : null,
      h('ol', { class: 'phrase-list', start: stage.from }, phrases.map((p) =>
        h('li', {},
          h('span', { class: 'pl-kanji' }, p.kanji),
          h('span', { class: 'pl-yomi' }, p.yomi.join('')),
          masteryDots(p.id, '読みの記憶度'),
          masteryDots(meaningKey(p.id), '意味の記憶度'),
          meaningEl(p, 'opt'))))),
    open ? null : h('p', { class: 'notice' }, '前の段を成就すると、ゲームが遊べるようになります。経本モードはいつでも読めます。'),
    h('h3', { class: 'section-title' }, '修行を選ぶ'),
    h('nav', { class: 'mode-grid' }, MODES.map(({ meta }, i) => {
      const enabled = open || meta.key === 'learn';
      return h('a', {
        class: `mode-card${enabled ? '' : ' locked'}`,
        href: enabled ? `#/play/${meta.key}/${stage.id}` : null,
        'aria-disabled': enabled ? null : 'true',
      },
      h('span', { class: 'mode-no' }, '①②③④⑤⑥'[i]),
      h('strong', {}, meta.title),
      h('span', { class: 'muted small' }, meta.desc));
    }))));
  return bar.off;
}
