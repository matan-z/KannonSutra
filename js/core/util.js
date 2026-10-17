export function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// kanji が重複しない候補を集める（念彼観音力のような繰り返し句対策）
export function uniqueByKanji(phrases) {
  const seen = new Set();
  return phrases.filter((p) => !seen.has(p.kanji) && seen.add(p.kanji));
}
