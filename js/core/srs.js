// 句ごとの記憶度（Leitner 方式、箱 0〜5）。0 = 未学習、3 以上 = 覚えた。
import { store } from './store.js';

export const MAX_BOX = 5;
export const MASTERED = 3;

// 読みの記憶度は句 ID（1, 2, …）、意味の記憶度は 'm1', 'm2', … で記録する
export const meaningKey = (id) => `m${id}`;
export const boxOf = (id) => store.get().srs[id]?.box ?? 0;
export const isMastered = (id) => boxOf(id) >= MASTERED;

// grade: 'good'（正解）| 'fair'（あやしい）| 'bad'（間違い）
export function record(id, grade) {
  let box = 0;
  store.update((s) => {
    const cur = s.srs[id] ?? { box: 0, seen: 0, miss: 0 };
    if (grade === 'good') cur.box = Math.min(MAX_BOX, cur.box + 1);
    else if (grade === 'fair') cur.box = Math.max(1, cur.box);
    else { cur.box = 1; cur.miss += 1; }
    cur.seen += 1;
    cur.last = Date.now();
    s.srs[id] = cur;
    box = cur.box;
  });
  return box;
}

// 記憶度が低い句ほど選ばれやすい重み
const weight = (id) => (MAX_BOX + 1 - boxOf(id)) ** 2;

// 重複なしで n 件を重み付き抽選
export function pickWeighted(items, n, idOf = (x) => x.id) {
  const pool = [...items];
  const out = [];
  while (out.length < n && pool.length) {
    const total = pool.reduce((sum, x) => sum + weight(idOf(x)), 0);
    let r = Math.random() * total;
    let i = 0;
    for (; i < pool.length - 1; i++) {
      r -= weight(idOf(pool[i]));
      if (r <= 0) break;
    }
    out.push(pool.splice(i, 1)[0]);
  }
  return out;
}
