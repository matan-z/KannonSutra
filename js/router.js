// ハッシュルーター。screen(root, params) は後片付け関数を返せる。
export function createRouter(root, routes) {
  const compiled = routes.map(([pattern, screen]) => {
    const keys = [];
    const re = new RegExp(`^${pattern.replace(/:(\w+)/g, (_, k) => { keys.push(k); return '([^/]+)'; })}$`);
    return { re, keys, screen };
  });
  let cleanup = null;

  function render() {
    const path = location.hash.slice(1) || '/';
    cleanup?.();
    cleanup = null;
    root.replaceChildren();
    for (const r of compiled) {
      const m = path.match(r.re);
      if (!m) continue;
      const params = Object.fromEntries(r.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]));
      cleanup = r.screen(root, params) ?? null;
      window.scrollTo(0, 0);
      return;
    }
    go('/');
  }

  addEventListener('hashchange', render);
  render();
}

export const go = (path) => { location.hash = `#${path}`; };
