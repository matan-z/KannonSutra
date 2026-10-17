// 進捗と設定を localStorage に保存する。保存できない環境でもメモリ上で動く。
const KEY = 'kannongyo-sekaige:v1';

const DEFAULTS = {
  settings: { ruby: true, meaning: true, vertical: true, fontSize: 'm', bpm: 72, freePlay: false },
  srs: {},
  stats: { merit: 0, bestCombo: 0 },
};

function merge(base, saved) {
  for (const [k, v] of Object.entries(saved ?? {})) {
    const isObj = (x) => x && typeof x === 'object' && !Array.isArray(x);
    if (isObj(base[k]) && isObj(v)) merge(base[k], v);
    else base[k] = v;
  }
  return base;
}

function read() {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return merge(structuredClone(DEFAULTS), JSON.parse(raw));
  } catch { /* プライベートモード等 */ }
  return structuredClone(DEFAULTS);
}

let state = read();
const subscribers = new Set();

function persist() {
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* 保存不可でも続行 */ }
  subscribers.forEach((fn) => fn(state));
}

export const store = {
  get: () => state,
  update(fn) {
    fn(state);
    persist();
  },
  subscribe(fn) {
    subscribers.add(fn);
    return () => subscribers.delete(fn);
  },
  resetProgress() {
    state = { ...structuredClone(DEFAULTS), settings: state.settings };
    persist();
  },
};
