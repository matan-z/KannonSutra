#!/usr/bin/env python3
"""Reduce thumps/clicks and add room reverberation without changing speech timing."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.signal import butter, oaconvolve, sosfilt, sosfiltfilt
import soundfile as sf

from generate_audio import (ROOT, PROFILES, atomic_write, audio_stem, encode_mp3,
                            read_phrases, read_title, request, trim_wav_silence)

SETTINGS = {
    'recipe': 'clean-room-v1', 'highPassHz': 90, 'edgeFadeMs': 6,
    'declick': 'adeclick=w=25:o=75:a=2:t=6:b=2',
    'reverb': {'preDelayMs': 24, 'decaySeconds': .72, 'tailSeconds': .85, 'wetRatio': .28},
}


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def fade_edges(x, sr):
    y = np.array(x, dtype=np.float64, copy=True)
    n = min(round(sr * SETTINGS['edgeFadeMs'] / 1000), len(y) // 4)
    if n > 1:
        ramp = np.sin(np.linspace(0, np.pi / 2, n)) ** 2
        y[:n] *= ramp
        y[-n:] *= ramp[::-1]
    return y


def clean_edges(x, sr):
    if len(x) < 64 or rms(x) < 1e-6 or not np.all(np.isfinite(x)):
        raise ValueError('空・無音・不正な句の音声は処理できません。')
    # Zero-phase filtering preserves the timing and fundamental pitch of the voice.
    sos = butter(3, SETTINGS['highPassHz'], fs=sr, btype='highpass', output='sos')
    return fade_edges(sosfiltfilt(sos, x), sr)


def declick(x, sr):
    result = subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-threads', '1',
        '-filter_threads', '1', '-f', 'f32le', '-ar', str(sr), '-ac', '1', '-i', 'pipe:0',
        '-af', SETTINGS['declick'], '-f', 'f32le', '-ac', '1', 'pipe:1',
    ], input=np.asarray(x, dtype='<f4').tobytes(), capture_output=True)
    if result.returncode:
        raise RuntimeError('クリック除去に失敗しました: ' + result.stderr.decode(errors='replace')[-1000:])
    y = np.frombuffer(result.stdout, dtype='<f4').astype(np.float64)
    if len(y) != len(x) or not np.all(np.isfinite(y)):
        raise ValueError('クリック除去で音声の長さが変化しました。公開を中止します。')
    return y


def room_impulse(sr):
    config = SETTINGS['reverb']
    count = round(sr * config['tailSeconds']) + 1
    time = np.arange(count) / sr
    predelay = config['preDelayMs'] / 1000
    envelope = np.exp(-np.log(1000) * np.maximum(0, time - predelay) / config['decaySeconds'])
    noise = np.random.default_rng(20261017).normal(size=count) * envelope
    noise[time < predelay] = 0
    # Band-limited diffuse reflections avoid harsh, repeated syllables.
    noise = sosfilt(butter(2, [180, min(5000, sr * .4)], fs=sr, btype='bandpass', output='sos'), noise)
    impulse = noise * (.55 / np.linalg.norm(noise))
    for seconds, gain in [(.026, .5), (.043, .3), (.067, .2), (.091, .14), (.131, .1)]:
        impulse[round(seconds * sr)] += gain
    impulse[-round(.04 * sr):] *= np.linspace(1, 0, round(.04 * sr))
    return impulse


def reverberate(x, sr, impulse=None):
    if impulse is None:
        impulse = room_impulse(sr)
    # Overlap-add keeps the memory cost bounded for a ten-minute learning track.
    wet = oaconvolve(x, impulse, mode='full')
    if rms(wet[:len(x)]) < 1e-8:
        raise ValueError('残響の生成に失敗しました。')
    wet *= rms(x) / rms(wet[:len(x)])
    output = np.pad(x, (0, len(impulse) - 1)) + SETTINGS['reverb']['wetRatio'] * wet
    # Keep comparable loudness and leave MP3 encoding headroom.
    output *= rms(x) / rms(output[:len(x)])
    output *= min(1., .89 / float(np.max(np.abs(output))))
    return output


def synthesize_native(item, mode, speaker, engine, pitch_hz):
    query = request(engine, 'audio_query', params={'speaker': speaker, 'text': item['yomi']})
    for accent in query['accent_phrases']:
        for mora in accent['moras']:
            if mora['pitch'] > 0:
                mora['pitch'] = math.log(pitch_hz)
    query.update(speedScale=PROFILES[mode]['speed'], pitchScale=0., intonationScale=1.,
                 prePhonemeLength=.06, postPhonemeLength=.08,
                 outputSamplingRate=24000, outputStereo=False)
    audio = request(engine, 'synthesis', params={'speaker': speaker}, payload=query)
    return trim_wav_silence(audio)


def process(root=ROOT, native_pitch=False, engine='http://127.0.0.1:50021', manifest_override=None):
    manifest_path, data_path = root / 'assets/audio/manifest.json', root / 'js/data/sekai-ge.js'
    published_bytes, data_bytes = manifest_path.read_bytes(), data_path.read_bytes()
    manifest_bytes = published_bytes if manifest_override is None else json.dumps(manifest_override, ensure_ascii=False).encode()
    original = json.loads(manifest_bytes)
    phrases, title = read_phrases(data_path), read_title(data_path)
    reading = ([title] if title else []) + phrases
    recipe = {**SETTINGS, 'nativePitch': native_pitch}
    pitch_hz = original.get('pitchReference', {}).get('medianHz')
    speaker_id = None
    if native_pitch:
        if not pitch_hz or not 80 < pitch_hz < 300:
            raise ValueError('参考音声の基準音が必要です。')
        speakers = request(engine, 'speakers', timeout=5)
        speaker_id = next((style['id'] for speaker in speakers
                           if speaker['name'] == original['credit'].removeprefix('VOICEVOX:')
                           for style in speaker['styles'] if style['name'] == original['style']), None)
        if speaker_id is None:
            raise ValueError('以前と同じVOICEVOX話者が見つかりません。')
        recipe['pitchHz'] = pitch_hz
    digest = hashlib.sha256(manifest_bytes + data_bytes + json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:20]
    output_root = root / 'assets/audio/generated' / digest
    revised, validation = copy.deepcopy(original), []
    if native_pitch:
        revised['pitchReference']['method'] = 'VOICEVOX native mora F0; voiced moras use the reference median pitch'
    for mode in ['slow', 'continuous']:
        profile = original['profiles'][mode]
        folder = output_root / mode
        (folder / 'dry').mkdir(parents=True, exist_ok=True)
        clips, raw_clips, entries, source_paths = [], [], [], []
        rate = None
        for index, item in enumerate(reading):
            entry = profile.get('title', {}) if item['id'] == 'title' else profile['phrases'].get(str(item['id']), {})
            if (entry.get('kanji'), entry.get('yomi')) != (item['kanji'], item['yomi']):
                raise ValueError('経文と音声が一致しません。先に追加・変更された音声を生成してください。')
            # Always start from the original dry recording, even on a second run.
            if native_pitch:
                source_path = f'assets/audio/generated/{digest}/{mode}/source/{audio_stem(item)}.wav'
                if not (root / source_path).exists():
                    atomic_write(root / source_path, synthesize_native(item, mode, speaker_id, engine, pitch_hz))
                if index % 15 == 0:
                    print(f'{mode}: 合成時の音程指定で生成 {index + 1}/{len(reading)}', flush=True)
            else:
                source_path = entry.get('sourceWav', str(Path(entry['src']).with_suffix('.wav')))
            x, sr = sf.read(root / source_path, dtype='float64')
            if x.ndim != 1 or (rate is not None and sr != rate):
                raise ValueError('句ごとの音声形式が一致しません。')
            rate = sr
            if not native_pitch and abs(len(x) / sr - (entry['end'] - entry['start'])) > 1 / sr:
                raise ValueError('句ごとの音声の長さと再生位置が一致しません。')
            clips.append(clean_edges(x, sr))
            raw_clips.append(x)
            entries.append(entry)
            source_paths.append(source_path)
        print(f'{mode}: 低域の雑音とクリックを補正中', flush=True)
        # One continuous pass avoids resetting the de-clicker at each syllable.
        before = np.concatenate(clips)
        cleaned = declick(before, rate)
        cursor, starts = 0, []
        for i, clip in enumerate(clips):
            starts.append(cursor)
            clips[i] = fade_edges(cleaned[cursor:cursor + len(clip)], rate)
            cursor += len(clip)
        cleaned = np.concatenate(clips)
        # Filtering preserves every sample; re-synthesis gets freshly measured offsets.
        for entry, start in zip(entries, starts):
            if not native_pitch and abs(entry['start'] - start / rate) > 1 / rate:
                raise ValueError('句間0秒の音声が必要です。先に句間の無音を除去してください。')
        sf.write(folder / 'dry/full.wav', cleaned, rate, subtype='PCM_16')
        impulse = room_impulse(rate)
        full = reverberate(cleaned, rate, impulse)
        sf.write(folder / 'full.wav', full, rate, subtype='PCM_16')
        encode_mp3(folder / 'full.wav', original['credit'], f"観音経 経題と全{len(phrases)}句 {profile['label']} 雑音低減・残響付き")
        prefix = f'assets/audio/generated/{digest}/{mode}'
        revised_profile = revised['profiles'][mode]
        revised_profile.update(src=f'{prefix}/full.mp3', durationSeconds=len(full) / rate,
                               speechEndSeconds=len(cleaned) / rate, postProcessing=copy.deepcopy(recipe))
        for index, (item, entry, clip, source) in enumerate(zip(reading, entries, clips, source_paths)):
            stem = audio_stem(item)
            sf.write(folder / 'dry' / f'{stem}.wav', clip, rate, subtype='PCM_16')
            sf.write(folder / f'{stem}.wav', reverberate(clip, rate, impulse), rate, subtype='PCM_16')
            encode_mp3(folder / f'{stem}.wav', original['credit'], f"観音経 {profile['label']} {item['kanji']} 残響付き")
            updated = {**entry, 'src': f'{prefix}/{stem}.mp3', 'sourceWav': source,
                       'start': starts[index] / rate, 'end': (starts[index] + len(clip)) / rate}
            if native_pitch:
                updated['synthesis'] = {'method': 'VOICEVOX-native-F0', 'pitchHz': pitch_hz}
            if item['id'] == 'title':
                revised_profile['title'] = updated
            else:
                revised_profile['phrases'][str(item['id'])] = updated
            if index % 30 == 0:
                print(f'{mode}: 残響付き音声 {index + 1}/{len(reading)}', flush=True)
        raw_full = np.concatenate(raw_clips)
        jumps_before = [abs(raw_full[start] - raw_full[start-1]) for start in starts[1:]]
        jumps_after = [abs(cleaned[start] - cleaned[start-1]) for start in starts[1:]]
        validation.append({'mode': mode, 'speechSeconds': len(cleaned) / rate, 'seconds': len(full) / rate,
                           'peak': float(np.max(np.abs(full))), 'rms': rms(full[:len(cleaned)]),
                           'maxCleanJoinJump': float(max(jumps_after, default=0)),
                           'maxOriginalJoinJump': float(max(jumps_before, default=0)),
                           'declickDifferenceRms': rms(before - cleaned), 'segments': len(reading)})
    if manifest_path.read_bytes() != published_bytes or data_path.read_bytes() != data_bytes:
        raise RuntimeError('処理中に経文か音声設定が変更されたため、切り替えを中止しました。')
    atomic_write(root / f'assets/audio/manifest-before-polish-{digest}.json', published_bytes)
    atomic_write(output_root / 'audio-validation.json', json.dumps(validation, indent=2).encode())
    for mode in ['slow', 'continuous']:
        audio = (output_root / mode / 'full.mp3').read_bytes()
        for name in [f'kannongyo-complete-{mode}.mp3', f'kannongyo-sekaige-{mode}.mp3', f'kannongyo-sekaige-{mode}-tuned.mp3']:
            atomic_write(root / 'assets/audio' / name, audio)
        if title:
            atomic_write(root / f'assets/audio/kannongyo-title-{mode}.mp3', (output_root / mode / 'title.mp3').read_bytes())
    atomic_write(manifest_path, json.dumps(revised, ensure_ascii=False, indent=2).encode())
    print(json.dumps(validation, ensure_ascii=False), flush=True)
    return revised


def main():
    parser = argparse.ArgumentParser(description='雑音低減と残響の追加。--native-pitchで参考音程を合成時に直接指定')
    parser.add_argument('--native-pitch', action='store_true')
    parser.add_argument('--engine', default='http://127.0.0.1:50021')
    args = parser.parse_args()
    if not shutil.which('ffmpeg'):
        print('ffmpegが必要です。', file=sys.stderr)
        return 1
    try:
        process(native_pitch=args.native_pitch, engine=args.engine)
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
