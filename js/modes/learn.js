// ① 経本モード: 木魚のテンポで1字ずつ強調して読む。音声があれば音声に同期。
import { h, phraseEl, sutraText, meaningEl } from '../ui/components.js';
import { SUTRA_TITLE, verseLabel } from '../data/sekai-ge.js';
import { store } from '../core/store.js';
import { addMerit } from '../core/progress.js';
import { sleep } from '../core/util.js';
import * as audio from '../audio/audioService.js';

export const meta = { key: 'learn', title: '経本', desc: 'ゆっくり音声・通し読み・文字のガイドで覚える' };

export function mount(root, { phrases }) {
  const settings = () => store.get().settings;
  const kuEls = phrases.map((p) => phraseEl(p));
  const jis = kuEls.flatMap((k) => [...k.querySelectorAll('.ji')]);
  const starts = [];
  kuEls.reduce((n, k, i) => { starts[i] = n; return n + k.querySelectorAll('.ji').length; }, 0);

  let cursor = 0;
  let token = 0;
  let playing = false;
  let alive = true;
  let manifest = null;
  let titlePending = phrases[0].id === 1;
  let readingTitle = false;

  const text = sutraText(kuEls, { withTitle: phrases[0].id === 1 });
  const mokugyo = h('span', { class: 'mokugyo', 'aria-hidden': 'true' });
  const playBtn = h('button', { class: 'btn primary', onclick: () => (playing ? stopPlay() : play()) }, '▶ 読む');
  const bpmLabel = h('output', {}, settings().bpm);
  const bpm = h('input', {
    type: 'range', min: 40, max: 160, step: 4, value: settings().bpm, 'aria-label': 'テンポ',
    oninput: () => { bpmLabel.textContent = bpm.value; },
    onchange: () => store.update((s) => { s.settings.bpm = Number(bpm.value); }),
  });
  const rubyBtn = h('button', {
    class: 'btn ghost',
    onclick: () => store.update((s) => { s.settings.ruby = !s.settings.ruby; }),
  }, 'ルビ');
  const source = h('select', { 'aria-label': '読み方', onchange: () => { stopPlay(); describeSource(); } },
    h('option', { value: 'visual' }, '文字のガイド（音声なし）'),
    h('option', { value: 'slow', disabled: true }, 'ゆっくり覚える（音声未生成）'),
    h('option', { value: 'continuous', disabled: true }, '通し読み（音声未生成）'));
  const audioNote = h('p', { class: 'muted small audio-note', 'aria-live': 'polite' }, '音声を確認しています…');
  const bpmControl = h('label', { class: 'bpm' }, mokugyo, 'テンポ', bpm, bpmLabel);
  const status = h('p', { class: 'muted small', 'aria-live': 'polite' }, '字をタップするとそこから読み始めます');
  const meaningBtn = h('button', {
    class: 'btn ghost',
    onclick: () => store.update((s) => { s.settings.meaning = !s.settings.meaning; }),
  }, '訳');
  // 今読んでいる句を含む偈（4句）の現代語訳
  const verseBox = h('section', { class: 'verse-meaning' });
  let shownVerse = null;
  function showVerse(pi) {
    const v = phrases[pi].verse;
    if (v !== shownVerse) {
      shownVerse = v;
      verseBox.replaceChildren(h('p', { class: 'eyebrow' }, `${verseLabel(phrases[pi])} 現代語訳`),
        ...phrases.flatMap((p, j) => {
          if (p.verse !== v) return [];
          const el = meaningEl(p);
          el.dataset.pi = j;
          return [el];
        }));
    }
    verseBox.querySelectorAll('.meaning').forEach((el) => el.classList.toggle('on', Number(el.dataset.pi) === pi));
  }

  root.append(
    h('div', { class: 'toolbar' }, h('label', { class: 'audio-source' }, '読み方', source), playBtn, rubyBtn, meaningBtn, bpmControl),
    audioNote,
    text, verseBox, status);
  showVerse(0);

  function describeSource() {
    bpmControl.hidden = source.value !== 'visual';
    if (source.value === 'visual') {
      audioNote.textContent = manifest && ['slow', 'continuous'].some((key) => audio.hasRange(manifest.profiles[key], phrases))
        ? '読み方を切り替えると、音声を聞きながら練習できます。'
        : 'この範囲の音声はまだありません。文字のガイドで練習できます。';
    } else {
      audioNote.textContent = `${source.value === 'slow' ? 'ゆっくりした速さで続けて読み上げます。' : '選んだ範囲を続けて読み上げます。'} ${manifest.notice ?? '合成音声です。'} ${manifest.credit ?? ''}`;
    }
    status.textContent = source.value === 'visual' ? '字をタップするとそこから読み始めます' : '字をタップすると、その句の初めから聞けます';
  }

  audio.loadManifest().then((data) => {
    if (!alive) return;
    manifest = data;
    for (const key of ['slow', 'continuous']) {
      const option = source.querySelector(`[value="${key}"]`);
      const available = audio.hasRange(data.profiles[key], phrases);
      option.disabled = !available;
      if (available) option.textContent = key === 'slow' ? 'ゆっくり覚える' : '通し読み';
    }
    if (!playing && cursor === 0 && audio.hasRange(data.profiles.slow, phrases)) source.value = 'slow';
    describeSource();
  }).catch(() => { if (alive) audioNote.textContent = '音声の一覧を読み込めませんでした。文字のガイドは使えます。'; });

  function mark(g) {
    cursor = g;
    jis.forEach((el, j) => {
      el.classList.toggle('done', j < g);
      el.classList.toggle('on', j === g);
    });
    jis[g]?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
    if (g < jis.length) showVerse(starts.findLastIndex((s) => s <= g));
  }

  function beat() {
    mokugyo.classList.remove('hit');
    void mokugyo.offsetWidth;
    mokugyo.classList.add('hit');
  }

  async function play() {
    const my = ++token;
    playing = true;
    playBtn.textContent = '■ 止める';
    if (cursor >= jis.length) {
      cursor = 0;
      titlePending = phrases[0].id === 1;
    }
    const startPhrase = starts.findLastIndex((s) => s <= cursor);
    try {
      if (source.value !== 'visual') {
        const profile = manifest?.profiles[source.value];
        const ok = await audio.playRange(profile, phrases.slice(startPhrase), (relative, ratio) => {
          if (my !== token) return;
          if (relative === -1) {
            jis.forEach((el) => el.classList.remove('on', 'done'));
            if (!readingTitle) text.querySelector('.kyodai')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            readingTitle = true;
            status.textContent = `経題「${SUTRA_TITLE.kanji}」を読んでいます`;
            return;
          }
          titlePending = false;
          if (readingTitle) status.textContent = '字をタップすると、その句の初めから聞けます';
          readingTitle = false;
          const pi = startPhrase + relative;
          const len = kuEls[pi].querySelectorAll('.ji').length;
          mark(starts[pi] + Math.min(len - 1, Math.floor(ratio * len)));
        }, { includeTitle: titlePending && startPhrase === 0 && audio.hasTitle(profile, SUTRA_TITLE) });
        if (!ok || my !== token) return;
      } else {
        for (let pi = startPhrase; pi < phrases.length; pi++) {
          const len = kuEls[pi].querySelectorAll('.ji').length;
          const from = pi === startPhrase ? cursor - starts[pi] : 0;
          for (let ci = from; ci < len; ci++) {
            mark(starts[pi] + ci);
            beat();
            await sleep(60000 / Number(bpm.value));
            if (my !== token) return;
          }
        }
      }
      mark(jis.length);
      stopPlay();
      addMerit(5);
      status.textContent = '一通り読み終えました（功徳 +5）。もう一度読むか、ゲームで確かめましょう';
    } catch (error) {
      if (my !== token) return;
      stopPlay();
      status.textContent = error.message;
    }
  }

  function stopPlay() {
    token++;
    playing = false;
    audio.stop();
    playBtn.textContent = '▶ 読む';
    if (readingTitle) {
      readingTitle = false;
      status.textContent = '停止しました。「読む」で経題から再生します';
    }
  }

  text.addEventListener('click', (e) => {
    if (e.target.closest('.kyodai')) {
      const was = playing;
      stopPlay();
      cursor = 0;
      titlePending = true;
      mark(0);
      if (was) play();
      return;
    }
    const ji = e.target.closest('.ji');
    if (!ji) return;
    const was = playing;
    stopPlay();
    titlePending = false;
    mark(jis.indexOf(ji));
    if (was) play();
  });

  const onKey = (e) => {
    if (e.code === 'Space' && !(e.target instanceof Element && e.target.closest('input, button, select, a'))) {
      e.preventDefault();
      playing ? stopPlay() : play();
    }
  };
  addEventListener('keydown', onKey);
  return () => { alive = false; stopPlay(); removeEventListener('keydown', onKey); };
}
