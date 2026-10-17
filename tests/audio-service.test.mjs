import test from 'node:test';
import assert from 'node:assert/strict';
import * as audio from '../js/audio/audioService.js';

class FakeAudio extends EventTarget {
  duration = 10;
  currentTime = 0;
  constructor() { super(); FakeAudio.latest = this; }
  pause() { this.paused = true; }
  play() { this.paused = false; return Promise.resolve(); }
  load() { /* Tests decide when metadata is ready. */ }
}
globalThis.Audio = FakeAudio;
globalThis.document = { baseURI: 'http://localhost:8000/' };

test('range playback, cancellation before metadata, and file errors', async () => {
  const phrases = [
    { id: 1, kanji: '世尊妙相具', yomi: ['せ', 'そん', 'みょう', 'そう', 'ぐ'] },
    { id: 2, kanji: '我今重問彼', yomi: ['が', 'こん', 'じゅう', 'もん', 'ぴ'] },
  ];
  const profile = { src: 'assets/audio/full.wav', phrases: {
    1: { start: 0, end: 2, kanji: phrases[0].kanji, yomi: phrases[0].yomi.join('') },
    2: { start: 3, end: 5, kanji: phrases[1].kanji, yomi: phrases[1].yomi.join('') },
  } };
  assert.equal(audio.hasRange(profile, phrases), true);
  assert.equal(audio.hasRange(profile, [{ ...phrases[0], yomi: ['changed'] }]), false);
  const positions = [];
  const playing = audio.playRange(profile, phrases, (...position) => positions.push(position));
  const player = FakeAudio.latest;
  player.dispatchEvent(new Event('loadedmetadata'));
  player.currentTime = 4;
  player.dispatchEvent(new Event('timeupdate'));
  assert.deepEqual(positions.at(-1), [1, 0.5]);
  player.currentTime = 5;
  player.dispatchEvent(new Event('timeupdate'));
  assert.equal(await playing, true);
  assert.equal(player.paused, true);

  const pending = audio.playRange(profile, phrases);
  audio.stop();
  assert.equal(await pending, false);
  player.dispatchEvent(new Event('loadedmetadata'));
  assert.equal(player.paused, true, 'cancelled metadata must not start playback');

  const broken = audio.playRange(profile, phrases);
  player.dispatchEvent(new Event('error'));
  await assert.rejects(broken, /音声を再生できません/);

  const invalidLength = audio.playRange(profile, phrases);
  player.duration = 1;
  player.dispatchEvent(new Event('loadedmetadata'));
  await assert.rejects(invalidLength, /長さと再生区間/);
});

test('title precedes phrase 1 only when requested, then uses the same audio track', async () => {
  const title = { kanji: '経題', yomi: ['きょう', 'だい'] };
  const phrases = [{ id: 1, kanji: '世尊', yomi: ['せ', 'そん'] }, { id: 2, kanji: '如来', yomi: ['にょ', 'らい'] }];
  const profile = { src: 'assets/audio/with-title.mp3', speechEndSeconds: 6, durationSeconds: 6.85,
    title: { src: 'assets/audio/title.mp3', start: 0, end: 2, kanji: title.kanji, yomi: title.yomi.join('') },
    phrases: Object.fromEntries(phrases.map((p, i) => [p.id, {
      kanji: p.kanji, yomi: p.yomi.join(''), start: 2 + i * 2, end: 4 + i * 2,
    }])) };
  assert.equal(audio.hasTitle(profile, title), true);
  assert.equal(audio.hasTitle(profile, { ...title, yomi: ['changed'] }), false);
  const positions = [];
  const playing = audio.playRange(profile, phrases, (...p) => positions.push(p), { includeTitle: true });
  const player = FakeAudio.latest;
  player.duration = 10;
  player.dispatchEvent(new Event('loadedmetadata'));
  assert.equal(player.currentTime, 0);
  player.currentTime = 1;
  player.dispatchEvent(new Event('timeupdate'));
  assert.deepEqual(positions.at(-1), [-1, .5]);
  player.currentTime = 3;
  player.dispatchEvent(new Event('timeupdate'));
  assert.deepEqual(positions.at(-1), [0, .5]);
  player.currentTime = 6;
  player.dispatchEvent(new Event('timeupdate'));
  assert.equal(player.paused, false, 'the last reverb tail must not be cut off');
  player.currentTime = 6.85;
  player.dispatchEvent(new Event('timeupdate'));
  assert.equal(await playing, true);

  const bodyOnly = audio.playRange(profile, phrases);
  player.dispatchEvent(new Event('loadedmetadata'));
  assert.equal(player.currentTime, 2, 'tapping the first body phrase skips the title');
  audio.stop();
  assert.equal(await bodyOnly, false);

  const partial = audio.playRange(profile, phrases.slice(0, 1));
  player.dispatchEvent(new Event('loadedmetadata'));
  player.currentTime = 4;
  player.dispatchEvent(new Event('timeupdate'));
  assert.equal(await partial, true, 'partial stages do not extend into the next spoken phrase');

  const later = audio.playRange(profile, phrases.slice(1), null, { includeTitle: true });
  player.dispatchEvent(new Event('loadedmetadata'));
  assert.equal(player.currentTime, 4, 'later phrases never play the title');
  audio.stop();
  assert.equal(await later, false);
});
