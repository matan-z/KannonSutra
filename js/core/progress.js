// ステージ解放・功徳ポイント・コンボ。各モードは answer() を通して結果を記録する。
import { SUTRA } from '../data/sekai-ge.js';
import { store } from './store.js';
import { bus } from './events.js';
import * as srs from './srs.js';

export const ALL_STAGE = {
  id: 'all', title: '通し読経', name: `全${SUTRA.phrases.length}句`, from: 1, to: SUTRA.phrases.length,
};

export function getStage(id) {
  if (id === 'all') return ALL_STAGE;
  return SUTRA.stages.find((s) => String(s.id) === String(id)) ?? null;
}

export const stagePhrases = (stage) => SUTRA.phrases.slice(stage.from - 1, stage.to);

export function stageMastery(stage) {
  const ps = stagePhrases(stage);
  return ps.filter((p) => srs.isMastered(p.id)).length / ps.length;
}

export const isCleared = (stage) => stageMastery(stage) === 1;

export function stageMeaningMastery(stage) {
  const ps = stagePhrases(stage);
  return ps.filter((p) => srs.isMastered(srs.meaningKey(p.id))).length / ps.length;
}

export function isUnlocked(stage) {
  if (store.get().settings.freePlay) return true;
  if (stage.id === 'all') return SUTRA.stages.every(isCleared);
  if (stage.id === 1) return true;
  return isCleared(getStage(stage.id - 1));
}

let combo = 0;
export const resetCombo = () => { combo = 0; };

export function addMerit(n) {
  store.update((s) => { s.stats.merit += n; });
}

// track: 'reading'（読み）| 'meaning'（意味）。段の成就は読みの記憶度で判定する
export function answer(phraseId, grade, track = 'reading') {
  const clearedBefore = new Set(SUTRA.stages.filter(isCleared).map((s) => s.id));
  const box = srs.record(track === 'meaning' ? srs.meaningKey(phraseId) : phraseId, grade);
  combo = grade === 'good' ? combo + 1 : 0;
  const gain = grade === 'good' ? 10 + Math.min(combo, 10) * 2 : grade === 'fair' ? 3 : 0;
  store.update((s) => {
    s.stats.merit += gain;
    s.stats.bestCombo = Math.max(s.stats.bestCombo, combo);
  });
  bus.emit('answer', { phraseId, grade, combo, gain, box, track });
  for (const st of SUTRA.stages) {
    if (!clearedBefore.has(st.id) && isCleared(st)) bus.emit('stage:clear', { stage: st });
  }
  return { combo, gain, box };
}

export function summary() {
  const total = SUTRA.phrases.length;
  const memorized = SUTRA.phrases.filter((p) => srs.isMastered(p.id)).length;
  return {
    total,
    memorized,
    meanings: SUTRA.phrases.filter((p) => srs.isMastered(srs.meaningKey(p.id))).length,
    cleared: SUTRA.stages.filter(isCleared).length,
    merit: store.get().stats.merit,
    bestCombo: store.get().stats.bestCombo,
  };
}
