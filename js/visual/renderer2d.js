// 2D 演出（SVG + CSS アニメーション）。
// 同じ関数名（init / mountHome / lotusSVG）を持つ renderer3d.js を作れば差し替え可能。
const PETAL = 'M0 0 C -20 -28 -15 -72 0 -98 C 15 -72 20 -28 0 0 Z';

function lotusGroup(ratio) {
  const N = 9;
  const center = (N - 1) / 2;
  const spread = 7 + 11 * ratio;
  const byDist = [...Array(N).keys()].sort((a, b) => Math.abs(a - center) - Math.abs(b - center));
  const lit = new Set(byDist.slice(0, Math.round(ratio * N)));
  const petals = [...byDist].reverse().map((i) => {
    const d = Math.abs(i - center);
    return `<path d="${PETAL}" class="petal${lit.has(i) ? ' on' : ''}"
      transform="rotate(${(i - center) * spread}) scale(${1 - d * 0.05})"/>`;
  }).join('');
  return `<ellipse cx="0" cy="8" rx="70" ry="10" class="pad"/>${petals}`;
}

export function lotusSVG(ratio = 0) {
  return `<svg class="lotus" viewBox="-110 -110 220 135" role="img" aria-label="蓮の花">
    <g>${lotusGroup(ratio)}</g></svg>`;
}

function juzuBeads(lit, total = 108) {
  let s = '';
  for (let i = 0; i < total; i++) {
    const a = Math.PI / 2 + ((i + 0.5) / total) * Math.PI * 2;
    const x = (110 + 88 * Math.cos(a)).toFixed(1);
    const y = (105 + 88 * Math.sin(a)).toFixed(1);
    s += `<circle cx="${x}" cy="${y}" r="3.3" class="bead${i < lit ? ' on' : ''}"/>`;
  }
  return `${s}<line x1="110" y1="200" x2="110" y2="218" class="tassel"/>
    <circle cx="110" cy="195" r="7" class="bead mother"/>`;
}

// ホーム画面: 108玉の数珠の中に、覚えた割合だけ開く蓮
export function mountHome(el, { ratio, beads }) {
  el.innerHTML = `<svg class="home-visual" viewBox="0 0 220 222" role="img"
      aria-label="数珠 ${beads} / 108 玉、蓮 ${Math.round(ratio * 100)}%">
    ${juzuBeads(beads)}
    <g transform="translate(110 140) scale(.6)">${lotusGroup(ratio)}</g>
  </svg>`;
}

let layer = null;

function spawn(className, text, styles = {}) {
  if (!layer) return null;
  const s = document.createElement('span');
  s.className = className;
  if (text) s.textContent = text;
  for (const [k, v] of Object.entries(styles)) s.style.setProperty(k, v);
  s.addEventListener('animationend', () => s.remove());
  layer.append(s);
  return s;
}

function petals(n) {
  for (let i = 0; i < n; i++) {
    spawn('fx-petal', '', {
      '--x': `${35 + Math.random() * 30}vw`,
      '--dx': `${Math.random() * 36 - 18}vw`,
      '--r': `${Math.random() * 540 - 270}deg`,
      '--d': `${Math.random() * 180}ms`,
    });
  }
}

function bloom(title) {
  const box = document.createElement('div');
  box.className = 'fx-bloom';
  box.innerHTML = `<div class="fx-bloom-inner">${lotusSVG(1)}
    <p class="fx-bloom-title">${title}</p><p class="fx-bloom-sub">成就しました。次の段が開きます</p></div>`;
  const close = () => box.remove();
  box.addEventListener('click', close);
  setTimeout(close, 4000);
  layer.append(box);
}

export function init(bus, fxLayer) {
  layer = fxLayer;
  bus.on('answer', ({ grade, combo, gain }) => {
    if (grade !== 'good') return;
    petals(Math.min(4 + combo, 12));
    spawn('fx-gain', `+${gain}`);
    if (combo >= 3) spawn('fx-combo', `${combo} 連`);
  });
  bus.on('stage:clear', ({ stage }) => bloom(`${stage.title}「${stage.name}」`));
}
