import { h, topBar } from '../components.js';
import { getStage, stagePhrases, isUnlocked, resetCombo } from '../../core/progress.js';
import { getMode } from '../../modes/index.js';
import { go } from '../../router.js';

export function playScreen(root, { mode, id }) {
  const mod = getMode(mode);
  const stage = getStage(id);
  if (!mod || !stage) { go('/'); return null; }
  const unlocked = isUnlocked(stage);
  if (mode !== 'learn' && !unlocked) { go(`/stage/${id}`); return null; }

  const backHref = unlocked ? `#/stage/${id}` : '#/';
  const bar = topBar(mod.meta.title, backHref, `${stage.title}「${stage.name}」`);
  const body = h('main', { class: `play play-${mode}` });
  root.append(bar.el, body);

  let cleanup = null;
  const ctx = { stage, phrases: stagePhrases(stage), backHref, retry: start };
  function start() {
    cleanup?.();
    body.replaceChildren();
    resetCombo();
    cleanup = mod.mount(body, ctx) ?? null;
    window.scrollTo(0, 0);
  }
  start();

  return () => { cleanup?.(); bar.off(); };
}
