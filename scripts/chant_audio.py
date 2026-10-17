#!/usr/bin/env python3
"""Build a chant score with explicit Japanese vowels and reference-timed F0."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import gaussian_filter1d
import soundfile as sf

from generate_audio import (ROOT, atomic_write, audio_stem, encode_mp3, read_phrases, read_title, request)
from polish_audio import clean_edges, declick, reverberate
import polish_audio

FRAME_RATE = 93.75
BEAT_SECONDS = 2 / 3  # Repeated 0.67s pulse measured across the reference recording.
REFERENCE_START = 13.55
REFERENCE_URL = 'local-reference-recording'
SMALL = set('ャュョァィゥェォヮ')
VOWELS = {v: k for k, row in {
    'ア': 'アカガサザタダナハバパマヤラワ',
    'イ': 'イキギシジチヂニヒビピミリヰ',
    'ウ': 'ウクグスズツヅヌフブプムユルヴ',
    'エ': 'エケゲセゼテデネヘベペメレヱ',
    'オ': 'オコゴソゾトドノホボポモヨロヲ',
}.items() for v in row}
VOWELS.update({'ャ': 'ア', 'ュ': 'ウ', 'ョ': 'オ', 'ァ': 'ア', 'ィ': 'イ', 'ゥ': 'ウ', 'ェ': 'エ', 'ォ': 'オ'})


def kanji_moras(reading):
    """Treat long o/u/e/i as sustained vowels within one kanji, never across kanji."""
    kana = ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in reading)
    moras = []
    for char in kana:
        if char in SMALL:
            if not moras:
                raise ValueError('小書き仮名で読みを開始できません。')
            moras[-1] += char
        else:
            moras.append(char)
    result = []
    for mora in moras:
        previous_vowel = VOWELS.get(result[-1]['lyric'][-1]) if result else None
        long_vowel = result and (mora == previous_vowel or
                                (mora == 'ウ' and previous_vowel == 'オ') or
                                (mora == 'イ' and previous_vowel == 'エ'))
        if long_vowel or (mora == 'ー' and result):
            result[-1]['weight'] += 1
        elif mora == 'ン':
            result.append({'lyric': mora, 'weight': .65})
        elif mora == 'ッ':
            result.append({'lyric': mora, 'weight': .3})
        else:
            if mora[-1] not in VOWELS:
                raise ValueError(f'未知の読み: {mora}')
            result.append({'lyric': mora, 'weight': 1.})
    return result


def make_score(items, speed=1.):
    notes = [{'id': 'lead', 'key': None, 'frame_length': 15, 'lyric': ''}]
    frame_cursor = 15
    beat_cursor = 0.
    for item in items:
        for unit_index, unit in enumerate(item['yomiUnits']):
            moras = kanji_moras(unit)
            total = sum(m['weight'] for m in moras)
            local = 0.
            for mora_index, mora in enumerate(moras):
                local += mora['weight'] / total
                end = 15 + round((beat_cursor + local) * BEAT_SECONDS / speed * FRAME_RATE)
                length = end - frame_cursor
                if length < 2:
                    raise ValueError('モーラの時間が短すぎます。')
                notes.append({'id': f"{item['id']}:{unit_index}:{mora_index}", 'key': 52,
                              'frame_length': length, 'lyric': mora['lyric']})
                frame_cursor = end
            beat_cursor += 1
    notes.append({'id': 'tail', 'key': None, 'frame_length': 15, 'lyric': ''})
    return {'notes': notes}


def reference_pitch(path):
    data = np.load(path)
    times, f0 = data['times'], data['f0']
    selected = (times >= 30) & (times <= 370) & (f0 >= 145) & (f0 <= 185)
    if np.count_nonzero(selected) < 50:
        raise ValueError('参考音声から読経の音程を抽出できません。')
    median = float(np.median(f0[selected]))
    valid = (f0 >= median * 2**(-2.5/12)) & (f0 <= median * 2**(2.5/12))
    curve = np.interp(times, times[valid], np.log(f0[valid]))
    curve = gaussian_filter1d(curve, 3)
    return times, np.exp(curve), median


def render_block(items, engine, singer, reference, reference_offset=0., speed=1.):
    score = make_score(items, speed)
    query = request(engine, 'sing_frame_audio_query', params={'speaker': 6000}, payload=score)
    count = len(query['f0'])
    if len(query['volume']) != count or sum(p['frame_length'] for p in query['phonemes']) != count:
        raise ValueError('歌唱フレームの長さが一致しません。')
    times, hz, base = reference
    local_time = (np.arange(count) - 15) / FRAME_RATE
    target_time = REFERENCE_START + reference_offset + np.maximum(local_time, 0) * speed
    curve = np.interp(target_time, times, hz)
    f0 = np.asarray(query['f0'],dtype=float)
    voiced = f0 > 0
    # Retain the reference's small rises/falls instead of assigning one fixed note.
    f0[voiced] = curve[voiced]
    query['f0'] = f0.tolist()
    query.update(outputSamplingRate=24000, outputStereo=False, volumeScale=1.)
    audio = request(engine, 'frame_synthesis', params={'speaker': singer}, payload=query)
    x, sr = sf.read(io.BytesIO(audio), dtype='float64')
    if sr != 24000 or x.ndim != 1 or not np.all(np.isfinite(x)):
        raise ValueError('不正な音声が返されました。')
    # Boundaries follow actual consonant onsets, including their anticipation of a beat.
    starts, cursor = {}, 0
    for phoneme in query['phonemes']:
        note_id = phoneme.get('note_id') or ''
        pid = note_id.split(':')[0]
        if pid in {str(p['id']) for p in items} and pid not in starts:
            starts[pid] = round(cursor / FRAME_RATE * sr)
        cursor += phoneme['frame_length']
    if len(starts) != len(items):
        raise ValueError('音素に句のIDがありません。')
    end = round((count - 15) / FRAME_RATE * sr)
    result = []
    for i, item in enumerate(items):
        start = starts[str(item['id'])]
        stop = starts[str(items[i+1]['id'])] if i+1 < len(items) else end
        result.append(x[start:stop])
    return result, query


def preview(args):
    phrases = read_phrases(with_units=True)
    items = [phrases[i-1] for i in [1, 5, 21, 34]]
    reference = reference_pitch(args.reference_pitch)
    folder = ROOT/'assets/audio/previews/chant'
    folder.mkdir(parents=True,exist_ok=True)
    for singer in args.singers:
        clips, query = render_block(items,args.engine,singer,reference,reference_offset=12.)
        dry = declick(np.concatenate([clean_edges(x,24000) for x in clips]),24000)
        wet = reverberate(dry,24000)
        path = folder/f'chant-{singer}.wav'
        sf.write(path,wet,24000,subtype='PCM_16')
        credit = f"VOICEVOX:{'麒ヶ島宗麟' if singer == 3053 else '青山龍星'}"
        encode_mp3(path,credit,'観音経 発音・拍・抑揚の試聴版')
        atomic_write(path.with_suffix('.json'),json.dumps(query,ensure_ascii=False).encode())
        print(str(path.with_suffix('.mp3')),flush=True)


def publish(args):
    manifest_path = ROOT/'assets/audio/manifest.json'
    data_path = ROOT/'js/data/sekai-ge.js'
    previous, data_bytes = manifest_path.read_bytes(), data_path.read_bytes()
    original = json.loads(previous)
    phrases = read_phrases(with_units=True)
    title = read_title(with_units=True)
    reading = [title] + phrases
    singer = args.singers[0]
    if singer not in {3053,3013}:
        raise ValueError('対応している声は3053・3013です。')
    recipe = {'method':'VOICEVOX-frame-chant-v1','frameSinger':singer,
              'beatSeconds':BEAT_SECONDS,'referenceStart':REFERENCE_START,
              'url':REFERENCE_URL,'longVowels':'normalized within each kanji'}
    digest = hashlib.sha256(previous + data_bytes + args.reference_pitch.read_bytes() +
                            json.dumps(recipe,sort_keys=True).encode()).hexdigest()[:20]
    folder = ROOT/'assets/audio/generated'/digest
    folder.mkdir(parents=True,exist_ok=True)
    reference = reference_pitch(args.reference_pitch)
    draft = copy.deepcopy(original)
    draft['credit'] = f"VOICEVOX:{'麒ヶ島宗麟' if singer == 3053 else '青山龍星'}"
    draft['pitchReference']['method'] = 'Reference F0 contour and 90 BPM kanji pulse; VOICEVOX frame synthesis'
    draft['chant'] = recipe
    # Keep phrase IDs and part boundaries stable. Each verse is one continuous
    # synthesis block, so the model sees the consonants of the next phrase.
    blocks = [[title]]
    for part in ['ge','prose']:
        selected = [p for p in phrases if p['part']==part]
        blocks += [selected[i:i+4] for i in range(0,len(selected),4)]
    for mode,speed in [('slow',.7),('continuous',1.)]:
        directory = folder/mode
        (directory/'source').mkdir(parents=True,exist_ok=True)
        profile = draft['profiles'][mode]
        for key in ['postProcessing','durationSeconds','speechEndSeconds']:
            profile.pop(key,None)
        prefix = f'assets/audio/generated/{digest}/{mode}'
        offset, sample_cursor = 0.,0
        profile['phrases'] = {}
        for bi,items in enumerate(blocks):
            paths = [directory/'source'/f'{audio_stem(p)}.wav' for p in items]
            query_path = directory/'source'/f'block-{bi:02d}.json'
            if all(p.exists() for p in paths) and query_path.exists():
                clips = [sf.read(p,dtype='float64')[0] for p in paths]
            else:
                clips,query = render_block(items,args.engine,singer,reference,offset,speed)
                for path,clip in zip(paths,clips):
                    sf.write(path,clip,24000,subtype='PCM_16')
                atomic_write(query_path,json.dumps(query,ensure_ascii=False).encode())
            for item,clip,path in zip(items,clips,paths):
                entry = {**item,'src':f'{prefix}/source/{audio_stem(item)}.mp3',
                         'sourceWav':path.relative_to(ROOT).as_posix(),
                         'start':sample_cursor/24000,'end':(sample_cursor+len(clip))/24000,
                         'synthesis':{'method':'VOICEVOX-frame-chant','styleId':singer}}
                if item['id']=='title':
                    profile['title']=entry
                else:
                    profile['phrases'][str(item['id'])]=entry
                sample_cursor += len(clip)
            offset += sum(len(p['kanji']) for p in items)*BEAT_SECONDS
            print(f'{mode}: 第{bi+1}/{len(blocks)}ブロック 発音・拍・抑揚を生成',flush=True)
        profile['gapSeconds'] = 0
        profile['src'] = f'{prefix}/source/full.mp3'
    if manifest_path.read_bytes()!=previous or data_path.read_bytes()!=data_bytes:
        raise RuntimeError('生成中に経文か音声設定が変わったため、公開を中止しました。')
    atomic_write(folder/'chant-settings.json',json.dumps(recipe,ensure_ascii=False,indent=2).encode())
    # Publish the mastered full tracks atomically; no incomplete draft is exposed.
    return polish_audio.process(manifest_override=draft)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine',default='http://127.0.0.1:50021')
    parser.add_argument('--reference-pitch',type=Path,default=ROOT/'scripts/data/kannongyo-reference-pitch.npz')
    parser.add_argument('--singers',type=int,nargs='+',default=[3053,3013])
    parser.add_argument('--publish',action='store_true',help='指定した最初の声で全119句と経題を生成し公開')
    args=parser.parse_args()
    try:
        publish(args) if args.publish else preview(args)
    except (ValueError,RuntimeError,OSError,KeyError) as error:
        print(f'エラー: {error}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
