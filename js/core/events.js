// 小さなイベントバス。ゲームロジックはここに投げるだけで、
// 描画（2D / 将来の3D）や音声はこれを購読して反応する。
const listeners = new Map();

export const bus = {
  on(type, fn) {
    if (!listeners.has(type)) listeners.set(type, new Set());
    listeners.get(type).add(fn);
    return () => listeners.get(type).delete(fn);
  },
  emit(type, payload) {
    listeners.get(type)?.forEach((fn) => {
      try { fn(payload); } catch (e) { console.error(e); }
    });
  },
};
