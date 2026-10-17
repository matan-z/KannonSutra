#!/usr/bin/env python3
"""Remove phrase-edge silence and gaps from a published reading track."""
import argparse
import copy
import hashlib
import json
import shutil
import sys

from generate_audio import (ROOT, SILENCE_TRIM, atomic_write, audio_stem, combine, encode_mp3,
                            read_phrases, read_title, trim_wav_silence, wav_info)


def process(root=ROOT, mode='continuous'):
    if mode not in {'slow', 'continuous'}:
        raise ValueError('音声の種類はslowかcontinuousを指定してください。')
    manifest_path = root / 'assets/audio/manifest.json'
    data_path = root / 'js/data/sekai-ge.js'
    original_bytes, data_bytes = manifest_path.read_bytes(), data_path.read_bytes()
    original = json.loads(original_bytes)
    phrases = read_phrases(data_path)
    title = read_title(data_path)
    reading = ([title] if title else []) + phrases
    profile = original['profiles'][mode]
    label = profile['label']
    entry_for = lambda p: profile.get('title', {}) if p['id'] == 'title' else profile['phrases'].get(str(p['id']), {})
    for p in reading:
        entry = entry_for(p)
        if (entry.get('kanji'), entry.get('yomi')) != (p['kanji'], p['yomi']):
            raise ValueError('経文と公開中の音声が一致しません。先に追加・変更された句を生成してください。')
    recipe = json.dumps(SILENCE_TRIM, sort_keys=True).encode() + f'{mode}-zero-gap-v3-title'.encode()
    digest = hashlib.sha256(original_bytes + data_bytes + recipe).hexdigest()[:20]
    prefix = f'assets/audio/generated/{digest}/{mode}'
    folder = root / prefix
    folder.mkdir(parents=True, exist_ok=True)
    paths, removed_samples, sample_rate = [], 0, None
    for p in reading:
        entry = entry_for(p)
        source = root / entry['sourceWav'] if entry.get('sourceWav') else (root / entry['src']).with_suffix('.wav')
        before = source.read_bytes()
        after = trim_wav_silence(before)
        fmt, _, before_count = wav_info(before)
        _, _, after_count = wav_info(after)
        if sample_rate is not None and sample_rate != fmt[2]:
            raise ValueError('句ごとのサンプリング周波数が一致しません。')
        sample_rate = fmt[2]
        removed_samples += before_count - after_count
        path = folder / f"{audio_stem(p)}.wav"
        atomic_write(path, after)
        encode_mp3(path, original['credit'], f"観音経 {label} {p['id']} {p['kanji']}")
        paths.append(path)
    segments = combine(paths, folder / 'full.wav', 0)
    encode_mp3(folder / 'full.wav', original['credit'], f'観音経 世尊偈と結び 全{len(phrases)}句 {label} 句間なし')
    revised = copy.deepcopy(original)
    revised['profiles'][mode].update(
        src=f'{prefix}/full.mp3', gapSeconds=0, silenceTrim=dict(SILENCE_TRIM),
        phrases={str(p['id']): {**entry_for(p), **segment,
                              'src': f"{prefix}/{audio_stem(p)}.mp3"}
                 for p, segment in zip(reading, segments) if p['id'] != 'title'})
    if title:
        revised['profiles'][mode]['title'] = {**entry_for(title), **segments[0], 'src': f'{prefix}/title.mp3'}
    for key in ['postProcessing', 'durationSeconds', 'speechEndSeconds']:
        revised['profiles'][mode].pop(key, None)
    for entry in list(revised['profiles'][mode]['phrases'].values()) + ([revised['profiles'][mode]['title']] if title else []):
        entry.pop('sourceWav', None)
    if manifest_path.read_bytes() != original_bytes or data_path.read_bytes() != data_bytes:
        raise RuntimeError('生成中に音声設定か経文が変更されたため、公開の切り替えを中止しました。')
    atomic_write(root / f'assets/audio/manifest-before-timing-{digest}.json', original_bytes)
    audio = (folder / 'full.mp3').read_bytes()
    for name in [f'kannongyo-complete-{mode}.mp3', f'kannongyo-sekaige-{mode}.mp3',
                 f'kannongyo-sekaige-{mode}-tuned.mp3']:
        atomic_write(root / 'assets/audio' / name, audio)
    if title:
        atomic_write(root / f'assets/audio/kannongyo-title-{mode}.mp3', (folder / 'title.mp3').read_bytes())
    atomic_write(manifest_path, json.dumps(revised, ensure_ascii=False, indent=2).encode())
    print(json.dumps({'profile': mode, 'phraseCount': len(phrases), 'previousSeconds': profile['phrases'][str(phrases[-1]['id'])]['end'],
                      'seconds': segments[-1]['end'], 'edgeSilenceRemovedSeconds': removed_samples / sample_rate,
                      'gapSeconds': 0, 'src': f'{prefix}/full.mp3'}, ensure_ascii=False), flush=True)
    return revised


def main():
    parser = argparse.ArgumentParser(description='句間と各句の前後の無音を除去し、アプリの再生位置を更新')
    parser.add_argument('--profile', choices=['slow', 'continuous'], default='continuous')
    args = parser.parse_args()
    if not shutil.which('ffmpeg'):
        print('ffmpegが必要です。', file=sys.stderr)
        return 1
    try:
        process(mode=args.profile)
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f'エラー: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
