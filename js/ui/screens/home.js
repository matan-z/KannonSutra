import { h, meter } from '../components.js';
import { SUTRA, SUTRA_TITLE } from '../../data/sekai-ge.js';
import { summary, stageMastery, isCleared, isUnlocked, ALL_STAGE } from '../../core/progress.js';
import * as visual from '../../visual/index.js';

// 未解放の段に表示する鍵マーク（読み上げでは「未解放」）
function lockIcon() {
  const span = document.createElement('span');
  span.className = 'stage-first stage-lock';
  span.setAttribute('role', 'img');
  span.setAttribute('aria-label', '未解放');
  span.innerHTML = `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
    stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>
    <circle cx="12" cy="15.5" r="1.2" fill="currentColor" stroke="none"/></svg>`;
  return span;
}

export function homeScreen(root) {
  const s = summary();
  const ratio = s.memorized / s.total;
  const visualEl = h('div', { class: 'home-visual-wrap' });
  visual.mountHome(visualEl, { ratio, beads: Math.round(ratio * 108) });

  const stageCard = (st) => {
    const open = isUnlocked(st);
    const m = st.id === 'all' ? s.memorized / s.total : stageMastery(st);
    const first = SUTRA.phrases[st.from - 1].kanji;
    return h('a', {
      class: `stage-card${open ? '' : ' locked'}${st.id !== 'all' && isCleared(st) ? ' cleared' : ''}`,
      href: open ? `#/stage/${st.id}` : null,
      'aria-disabled': open ? null : 'true',
    },
    h('span', { class: 'stage-no' }, st.title),
    h('span', { class: 'stage-name' }, st.name),
    open ? h('span', { class: 'stage-first' }, `${first}…`) : lockIcon(),
    meter(m, `${st.title} の記憶度`));
  };

  root.append(
    h('header', { class: 'hero' },
      h('p', { class: 'eyebrow' }, SUTRA_TITLE.kanji),
      h('h1', {}, '観音経 暗記道場'),
      h('p', { class: 'lead' }, `世尊偈から結びまで ${SUTRA.phrases.length}句を、遊びながら一句ずつ。`)),
    h('section', { class: 'home-status' },
      visualEl,
      h('dl', { class: 'stats' },
        h('div', {}, h('dt', {}, '覚えた句'), h('dd', {}, h('strong', {}, s.memorized), ` / ${s.total}`)),
        h('div', {}, h('dt', {}, '覚えた意味'), h('dd', {}, h('strong', {}, s.meanings), ` / ${s.total}`)),
        h('div', {}, h('dt', {}, '成就した段'), h('dd', {}, h('strong', {}, s.cleared), ` / ${SUTRA.stages.length}`)),
        h('div', {}, h('dt', {}, '功徳'), h('dd', {}, h('strong', {}, s.merit))),
        h('div', {}, h('dt', {}, '最高連続'), h('dd', {}, h('strong', {}, s.bestCombo))))),
    h('div', { class: 'row home-actions' },
      h('a', { class: 'btn primary', href: '#/play/learn/all' }, '通しで読む（経本）'),
      h('a', { class: 'btn', href: '#/settings' }, '設定')),
    h('h2', { class: 'section-title' }, '段を選ぶ'),
    h('p', { class: 'muted small' }, '段のすべての句を「記憶度3」まで上げると成就し、次の段が開きます。'),
    h('nav', { class: 'stage-grid' }, SUTRA.stages.map(stageCard), stageCard(ALL_STAGE)));
}
