#!/usr/bin/env python3
"""Retune the existing synthetic reading using the pitch range of a reference WAV.

Requires numpy, scipy, soundfile and pyworld. The reference is used for F0 only.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pyworld as pw
from scipy.ndimage import gaussian_filter1d
import soundfile as sf

from generate_audio import (ROOT, PROFILES, SILENCE_TRIM, atomic_write, audio_stem, combine,
                            encode_mp3, read_phrases, read_title, request, trim_wav_silence, wav_info)

FRAME_MS = 10.0
REFERENCE_URL = 'local-reference-recording'


def read_audio(path):
    x, sr = sf.read(path, dtype='float64')
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr < 16000 or not len(x):
        raise ValueError('16kHz以上の空でない音声ファイルが必要です。')
    return np.ascontiguousarray(x), sr


def extract_pitch(x, sr, floor=55):
    f0, times = pw.dio(x, sr, f0_floor=floor, f0_ceil=400, frame_period=FRAME_MS)
    return pw.stonemask(x, f0, times, sr), times


def reference_curve(path, start, end):
    x, sr = read_audio(path)
    if not 0 <= start < end <= len(x) / sr:
        raise ValueError('参考音声の解析範囲が音声の長さと一致しません。')
    # Only the chosen chanting section contributes to the estimate.
    section = np.ascontiguousarray(x[round(start * sr):round(end * sr)])
    f0, times = extract_pitch(section, sr)
    voiced = f0 > 0
    if voiced.sum() < 100:
        raise ValueError('参考音声から十分な有声音を検出できませんでした。')
    midi = 69 + 12 * np.log2(f0[voiced] / 440)
    hist, edges = np.histogram(midi, bins=np.arange(20, 85, 0.25))
    mode_note = (edges[hist.argmax()] + edges[hist.argmax() + 1]) / 2
    notes = np.full_like(f0, np.nan)
    notes[voiced] = midi
    # Exclude octave errors, non-voice tones and spoken intros/outros.
    valid = voiced & (np.abs(notes - mode_note) < 3)
    if valid.sum() < 100:
        raise ValueError('参考音声の基準音を推定できませんでした。')
    base = float(np.median(f0[valid]))
    low, high = np.quantile(notes[valid], [.1, .9])
    note_curve = np.interp(times, times[valid], notes[valid])
    note_curve = gaussian_filter1d(np.clip(note_curve, low, high), sigma=20)
    hz_curve = 440 * 2 ** ((note_curve - 69) / 12)
    return times / (end - start), hz_curve, {
        'url': REFERENCE_URL, 'startSeconds': start, 'endSeconds': end,
        'medianHz': round(base, 3), 'pitchRangeHz': [round(float(440 * 2 ** ((v - 69) / 12)), 3) for v in [low, high]],
        'method': 'WORLD F0 correction; reference contour normalized across the reading',
    }


def retune(x, sr, reference_x, reference_hz, phrase_index, total):
    f0, times = extract_pitch(x, sr, floor=45)
    voiced = f0 > 0
    if voiced.sum() < 5:
        raise ValueError('合成音声の音程を検出できませんでした。')
    sp = pw.cheaptrick(x, f0, times, sr, f0_floor=45)
    ap = pw.d4c(x, f0, times, sr, fft_size=2 * (sp.shape[1] - 1))
    first, last = times[voiced][[0, -1]]
    local_position = np.clip((times - first) / max(last - first, .01), 0, 1)
    reference_position = (phrase_index + local_position) / total
    revised_f0 = np.zeros_like(f0)
    revised_f0[voiced] = np.interp(reference_position[voiced], reference_x, reference_hz)
    y = pw.synthesize(revised_f0, sp, ap, sr, FRAME_MS)
    y = np.pad(y, (0, max(0, len(x) - len(y))))[:len(x)]
    source_rms = float(np.sqrt(np.mean(x * x)))
    revised_rms = float(np.sqrt(np.mean(y * y)))
    if revised_rms < 1e-6:
        raise ValueError('音程調整後の音声が無音です。')
    y *= source_rms / revised_rms
    peak = float(np.max(np.abs(y)))
    if peak > .93:
        y *= .93 / peak
    return y


def process(args):
    manifest_path = ROOT / 'assets/audio/manifest.json'
    original_bytes = manifest_path.read_bytes()
    original = json.loads(original_bytes)
    data_path = ROOT / 'js/data/sekai-ge.js'
    original_data = data_path.read_bytes()
    phrases = read_phrases()
    title = read_title(data_path)
    reading = ([title] if title else []) + phrases
    entry_for = lambda profile, p: profile.get('title') if p['id'] == 'title' else profile['phrases'].get(str(p['id']))
    reference_x, reference_hz, metadata = reference_curve(args.reference, args.start, args.end)
    previous_reference = original.get('pitchReference', {})
    same_reference = all(previous_reference.get(key) == metadata[key]
                         for key in ['url', 'startSeconds', 'endSeconds', 'medianHz', 'pitchRangeHz'])
    matches = lambda entry, p: entry and entry.get('kanji') == p['kanji'] and entry.get('yomi') == p['yomi']
    missing = [p for p in reading if any(not matches(entry_for(original['profiles'][mode], p), p)
                                        for mode in ['slow', 'continuous'])]
    speaker_id = None
    if missing:
        speakers = request(args.engine, 'speakers', timeout=5)
        speaker_name = original['credit'].removeprefix('VOICEVOX:')
        speaker_id = next((style['id'] for speaker in speakers if speaker['name'] == speaker_name
                           for style in speaker['styles'] if style['name'] == original['style']), None)
        if speaker_id is None:
            raise ValueError('以前と同じ話者・スタイルがVOICEVOXにありません。')
    identity = original_bytes + original_data + args.reference.read_bytes() + json.dumps(metadata, sort_keys=True).encode() + b'world-pitch-v5-title'
    digest = hashlib.sha256(identity).hexdigest()[:20]
    output_root = ROOT / 'assets/audio/generated' / digest
    revised = copy.deepcopy(original)
    revised['pitchReference'] = metadata
    revised['phraseCount'] = len(phrases)
    revised['partCounts'] = {part: sum(p['part'] == part for p in phrases) for part in ['ge', 'prose']}
    revised['notice'] = '合成音声の音程を参考動画に合わせて調整しています。宗派固有の読経を厳密に再現したものではありません。'
    print('Reference pitch:', json.dumps(metadata, ensure_ascii=False), flush=True)
    validation = []
    for mode in ['slow', 'continuous']:
        profile = original['profiles'][mode]
        folder = output_root / mode
        folder.mkdir(parents=True, exist_ok=True)
        paths = []
        for index, phrase in enumerate(reading):
            pid = str(phrase['id'])
            old_entry = entry_for(profile, phrase)
            destination = folder / f'{audio_stem(phrase)}.wav'
            reused = False
            if matches(old_entry, phrase):
                source = ROOT / old_entry['sourceWav'] if old_entry.get('sourceWav') else (ROOT / old_entry['src']).with_suffix('.wav')
                x, sr = read_audio(source)
                if same_reference:
                    shutil.copyfile(source, destination)
                    if old_entry.get('sourceWav'):
                        encode_mp3(destination, original['credit'], f"音程調整版 {profile['label']} {pid} {phrase['kanji']}")
                    else:
                        shutil.copyfile(ROOT / old_entry['src'], destination.with_suffix('.mp3'))
                    reused = True
                    y = x
            else:
                query = request(args.engine, 'audio_query', params={'speaker': speaker_id, 'text': phrase['yomi']})
                query.update(speedScale=PROFILES[mode]['speed'], intonationScale=.3,
                             prePhonemeLength=.06, postPhonemeLength=.08,
                             outputSamplingRate=24000, outputStereo=False)
                raw = request(args.engine, 'synthesis', params={'speaker': speaker_id}, payload=query)
                wav_info(raw)
                source = folder / 'raw' / f'{audio_stem(phrase)}.wav'
                atomic_write(source, raw)
                x, sr = read_audio(source)
            if not reused:
                if phrase['part'] in {'prose', 'title'}:
                    # The title and closing prose follow the same stable base tone;
                    # the verse reference does not provide their exact word alignment.
                    curve_x, curve_hz = np.array([0., 1.]), np.array([metadata['medianHz']] * 2)
                else:
                    curve_x, curve_hz = reference_x, reference_hz
                y = retune(x, sr, curve_x, curve_hz, index, len(reading))
                sf.write(destination, y, sr, subtype='PCM_16')
                encode_mp3(destination, original['credit'], f"音程調整版 {profile['label']} {pid} {phrase['kanji']}")
            if pid in ['title', '1', '3', '7', str(phrases[-1]['id'])] or not reused:
                measured, _ = extract_pitch(np.ascontiguousarray(y), sr)
                median = float(np.median(measured[measured > 0]))
                error = abs(12 * np.log2(median / metadata['medianHz']))
                if not np.isfinite(error) or error > 1.5:
                    raise ValueError(f'{mode} {pid}句目の調整後の音程が基準音から外れています。')
                validation.append({'mode': mode, 'phrase': phrase['id'], 'medianHz': round(median, 3)})
            before = destination.read_bytes()
            trimmed = trim_wav_silence(before)
            if trimmed != before:
                atomic_write(destination, trimmed)
                encode_mp3(destination, original['credit'], f"音程調整版 {profile['label']} {pid} {phrase['kanji']}")
            paths.append(destination)
            print(f'{mode}: {pid} {"既存音声を再利用" if reused else "生成・音程調整"}', flush=True)
        gap = PROFILES[mode]['gap']
        segments = combine(paths, folder / 'full.wav', gap)
        encode_mp3(folder / 'full.wav', original['credit'], f"観音経 世尊偈と結び 全{len(phrases)}句 {profile['label']} 音程調整版{' 経題付き' if title else ''}")
        prefix = f'assets/audio/generated/{digest}/{mode}'
        revised['profiles'][mode]['src'] = f'{prefix}/full.mp3'
        for key in ['postProcessing', 'durationSeconds', 'speechEndSeconds']:
            revised['profiles'][mode].pop(key, None)
        revised['profiles'][mode]['gapSeconds'] = gap
        revised['profiles'][mode]['silenceTrim'] = dict(SILENCE_TRIM)
        revised['profiles'][mode]['phrases'] = {
            str(p['id']): {**p, **segment, 'src': f"{prefix}/{audio_stem(p)}.mp3"}
            for p, segment in zip(reading, segments) if p['id'] != 'title'
        }
        if title:
            revised['profiles'][mode]['title'] = {**title, **segments[0], 'src': f'{prefix}/title.mp3'}
        else:
            revised['profiles'][mode].pop('title', None)
    atomic_write(output_root / 'pitch-validation.json', json.dumps({'reference': metadata, 'samples': validation}, indent=2).encode())
    # A concurrent edit or regeneration must never be overwritten by this job.
    if manifest_path.read_bytes() != original_bytes or data_path.read_bytes() != original_data:
        raise RuntimeError('生成中に音声設定が変更されました。新しい音声は保存しましたが、自動切り替えを中止しました。')
    backup_path = ROOT / 'assets/audio' / f'manifest-before-pitch-{digest}.json'
    atomic_write(backup_path, original_bytes)
    for mode in ['slow', 'continuous']:
        audio = (output_root / mode / 'full.mp3').read_bytes()
        atomic_write(ROOT / f'assets/audio/kannongyo-sekaige-{mode}-tuned.mp3', audio)
        atomic_write(ROOT / f'assets/audio/kannongyo-sekaige-{mode}.mp3', audio)
        atomic_write(ROOT / f'assets/audio/kannongyo-complete-{mode}.mp3', audio)
        if title:
            atomic_write(ROOT / f'assets/audio/kannongyo-title-{mode}.mp3', (output_root / mode / 'title.mp3').read_bytes())
    atomic_write(manifest_path, json.dumps(revised, ensure_ascii=False, indent=2).encode())
    print(f'全{len(phrases)}句 × 2種類の音程調整とアプリの切り替えが完了しました。', flush=True)
    return revised


def main():
    parser = argparse.ArgumentParser(description='参考音声の安定した音程に合わせて既存の合成音声を調整')
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--engine', default='http://127.0.0.1:50021', help='追加・変更された句の生成に使うVOICEVOX API')
    parser.add_argument('--start', default=40., type=float, help='参考音声の読経部分の開始秒')
    parser.add_argument('--end', default=370., type=float, help='参考音声の読経部分の終了秒')
    args = parser.parse_args()
    if not shutil.which('ffmpeg'):
        parser.error('ffmpegが必要です。')
    try:
        process(args)
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
