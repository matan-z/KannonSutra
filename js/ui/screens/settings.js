import { h, topBar } from '../components.js';
import { store } from '../../core/store.js';

const SIZES = [['s', '小'], ['m', '中'], ['l', '大'], ['xl', '特大']];

export function settingsScreen(root) {
  const bar = topBar('設定', '#/');
  const s = () => store.get().settings;
  const set = (k, v) => store.update((st) => { st.settings[k] = v; });

  const toggle = (key, label, note) => h('label', { class: 'setting' },
    h('span', {}, h('strong', {}, label), note ? h('small', { class: 'muted' }, note) : null),
    h('input', { type: 'checkbox', checked: s()[key], onchange: (e) => set(key, e.target.checked) }));

  const sizeSel = h('select', { onchange: (e) => set('fontSize', e.target.value) },
    SIZES.map(([v, l]) => h('option', { value: v, selected: s().fontSize === v }, l)));

  root.append(bar.el, h('main', { class: 'settings' },
    h('section', { class: 'card' },
      toggle('ruby', 'ふりがな（ルビ）を表示', '慣れてきたら消してみましょう'),
      toggle('meaning', '現代語訳を表示', '経本・段の一覧・ひとり読経の答え'),
      toggle('vertical', '経本のように縦書き', '経本・ひとり読経の表示'),
      h('label', { class: 'setting' }, h('strong', {}, '文字の大きさ'), sizeSel),
      toggle('freePlay', 'すべての段を解放', '順番に関係なく練習したいとき')),
    h('section', { class: 'card danger' },
      h('h3', {}, '記録を消す'),
      h('p', { class: 'muted small' }, '記憶度・功徳をすべて0に戻します（設定は残ります）。'),
      h('button', {
        class: 'btn',
        onclick: () => {
          if (confirm('記録をすべて消しますか？')) { store.resetProgress(); location.hash = '#/'; }
        },
      }, '記録を消す'))));
  return bar.off;
}
