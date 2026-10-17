#!/usr/bin/env python3
"""Generate two VOICEVOX reading tracks using only the Python standard library."""
import argparse
from array import array
import ast
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    "slow": {"label": "ゆっくり覚える", "speed": 0.7, "gap": 0.0},
    "continuous": {"label": "通し読み", "speed": 1.0, "gap": 0.0},
}
SILENCE_TRIM = {"thresholdDb": -52, "windowMs": 5, "paddingMs": 5}


def read_phrases(path=ROOT / "js/data/sekai-ge.js", with_units=False):
    # Parse the literal data only; never execute the JavaScript source.
    source = path.read_text(encoding="utf-8")
    phrases = []
    for name, part in [('ROWS', 'ge'), ('PROSE_ROWS', 'prose')]:
        match = re.search(r'const ' + name + r'\s*=\s*(\[.*?\n\]);', source, re.S)
        if not match:
            if name == 'ROWS':
                raise ValueError('経文データの ROWS が見つかりません。')
            continue
        rows = ast.literal_eval(re.sub(r"//[^\n]*", "", match[1]))
        if not isinstance(rows, list):
            raise ValueError(f'{name} は句の配列である必要があります。')
        for row in rows:
            number = len(phrases) + 1
            if not isinstance(row, (list, tuple)) or len(row) < 2 or not all(isinstance(v, str) for v in row[:2]):
                raise ValueError(f"{number}句目の形式が不正です。")
            # Additional columns (meanings and sentence numbers) do not affect speech.
            kanji, yomi = row[:2]
            if not kanji or len(kanji) != len(yomi.split()) or not yomi.strip():
                raise ValueError(f"{number}句目の漢字と読みの数が一致しません。")
            phrases.append({"id": number, "part": part, "kanji": kanji, "yomi": "".join(yomi.split())})
            if with_units:
                phrases[-1]['yomiUnits'] = yomi.split()
    if not phrases:
        raise ValueError('経文データが空です。')
    return phrases


def read_title(path=ROOT / 'js/data/sekai-ge.js', with_units=False):
    """Read the literal title without executing JavaScript or renumbering phrases."""
    source = path.read_text(encoding='utf-8')
    match = re.search(r'export const SUTRA_TITLE\s*=\s*\{(.*?)\n\};', source, re.S)
    if not match:
        return None
    fields = {}
    for field in ['kanji', 'yomi']:
        literal = re.search(r'\b' + field + r'''\s*:\s*('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")''', match[1])
        if not literal:
            raise ValueError(f'経題の{field}が見つかりません。')
        fields[field] = ast.literal_eval(literal[1])
    if not fields['kanji'] or len(fields['kanji']) != len(fields['yomi'].split()):
        raise ValueError('経題の漢字と読みの数が一致しません。')
    result = {'id': 'title', 'part': 'title', 'kanji': fields['kanji'], 'yomi': ''.join(fields['yomi'].split())}
    if with_units:
        result['yomiUnits'] = fields['yomi'].split()
    return result


def audio_stem(item):
    return 'title' if item['id'] == 'title' else f"{item['id']:03d}"


def request(base, endpoint, *, params=None, payload=None, timeout=120):
    url = base.rstrip("/") + "/" + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    method = "POST" if payload is not None or endpoint in {"audio_query", "synthesis"} else "GET"
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    # Local synthesis must not be routed through an HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise RuntimeError(f"VOICEVOX /{endpoint}: HTTP {exc.code} {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"VOICEVOXに接続できません ({base})。VOICEVOXを起動して再実行してください。"
        ) from exc
    return body if endpoint in {'synthesis', 'frame_synthesis'} else json.loads(body)


def wav_info(data):
    with wave.open(io.BytesIO(data), "rb") as sound:
        fmt = (sound.getnchannels(), sound.getsampwidth(), sound.getframerate())
        count = sound.getnframes()
        frames = sound.readframes(count)
        if sound.getcomptype() != "NONE" or count == 0 or len(frames) != count * fmt[0] * fmt[1]:
            raise ValueError("空または不完全なWAVが返されました。")
        return fmt, frames, count


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def trim_wav_silence(data):
    """Trim only phrase edges; retain quiet consonants and pauses inside speech.

    Use 5ms RMS windows rather than individual samples to ignore low-level WORLD
    synthesis noise. A 5ms guard at either edge protects consonant attacks/tails.
    """
    fmt, frames, count = wav_info(data)
    channels, width, rate = fmt
    if width != 2:
        raise ValueError('無音除去には16-bit PCMのWAVが必要です。')
    samples = array('h')
    samples.frombytes(frames)
    if sys.byteorder != 'little':
        samples.byteswap()
    window = max(1, round(rate * SILENCE_TRIM['windowMs'] / 1000))
    padding = round(rate * SILENCE_TRIM['paddingMs'] / 1000)
    threshold_squared = (32768 * 10 ** (SILENCE_TRIM['thresholdDb'] / 20)) ** 2
    first, last = None, None
    for start in range(0, count, window):
        end = min(count, start + window)
        block = samples[start * channels:end * channels]
        if sum(v * v for v in block) / len(block) >= threshold_squared:
            if first is None:
                first = start
            last = end
    if first is None:
        raise ValueError('句の音声が無音のため、無音除去を中止しました。')
    first, last = max(0, first - padding), min(count, last + padding)
    if first == 0 and last == count:
        return data
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(frames[first * channels * width:last * channels * width])
    return buffer.getvalue()


def combine(paths, destination, gap):
    """Join PCM audio and return exact phrase offsets, derived from sample counts."""
    segments = []
    temporary = destination.with_suffix(".wav.tmp")
    reference = None
    frame_cursor = 0
    with wave.open(str(temporary), "wb") as output:
        for index, path in enumerate(paths):
            fmt, frames, count = wav_info(path.read_bytes())
            if reference is None:
                reference = fmt
                output.setnchannels(fmt[0])
                output.setsampwidth(fmt[1])
                output.setframerate(fmt[2])
            elif reference != fmt:
                raise ValueError("句ごとのWAV形式が異なるため結合できません。")
            segments.append({"start": frame_cursor / fmt[2], "end": (frame_cursor + count) / fmt[2]})
            output.writeframes(frames)
            frame_cursor += count
            if index < len(paths) - 1:
                silence_count = round(gap * fmt[2])
                # 8-bit PCM is unsigned; all other PCM widths are signed.
                zero = b"\x80" if fmt[1] == 1 else b"\x00" * fmt[1]
                output.writeframes(zero * fmt[0] * silence_count)
                frame_cursor += silence_count
    temporary.replace(destination)
    return segments


def encode_mp3(source, credit, title):
    destination = source.with_suffix('.mp3')
    temporary = destination.with_suffix('.mp3.tmp')
    result = subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
        '-i', str(source), '-map', '0:a:0', '-c:a', 'libmp3lame', '-b:a', '128k',
        '-id3v2_version', '3', '-metadata', f'artist={credit}', '-metadata', f'title={title}',
        '-metadata', 'comment=合成音声による学習用読み上げ。宗派固有の節回しは含みません。',
        '-f', 'mp3', str(temporary),
    ], capture_output=True, text=True)
    if result.returncode:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f'MP3への変換に失敗しました: {result.stderr[-1000:]}')
    temporary.replace(destination)
    return destination


def generate(phrases, speaker, engine_version, args, output_dir, api=request, title=None):
    reading = ([title] if title else []) + phrases
    output_format = getattr(args, 'format', 'wav')
    profiles = {key: dict(value) for key, value in PROFILES.items()}
    profiles["slow"]["speed"] = args.slow_speed
    profiles["slow"]["gap"] = args.slow_gap
    profiles["continuous"]["speed"] = args.continuous_speed
    identity = {"phrases": phrases, "title": title, "speaker": speaker, "version": engine_version, "profiles": profiles,
                "recipe": 4, "edgeSilenceTrim": SILENCE_TRIM}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    manifest = {"version": 1, "credit": f"VOICEVOX:{speaker['name']}",
                "style": speaker["style"], "engineVersion": engine_version,
                "notice": "合成音声による読み上げです。宗派固有の節回しは再現していません。",
                "profiles": {}}
    for key, profile in profiles.items():
        directory = output_dir / "generated" / digest / key
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for phrase in reading:
            stem = audio_stem(phrase)
            path = directory / f"{stem}.wav"
            cached = False
            if path.exists():
                try:
                    wav_info(path.read_bytes())
                    cached = True
                except (ValueError, wave.Error, EOFError):
                    pass
            if not cached:
                query = api(args.engine, "audio_query", params={"speaker": speaker["id"], "text": phrase["yomi"]})
                query.update(speedScale=profile["speed"], intonationScale=0.3,
                             prePhonemeLength=0.06, postPhonemeLength=0.08,
                             outputSamplingRate=24000, outputStereo=False)
                audio = api(args.engine, "synthesis", params={"speaker": speaker["id"]}, payload=query)
                wav_info(audio)
                audio = trim_wav_silence(audio)
                atomic_write(path, audio)
            print(f"{key}: {stem} {phrase['kanji']} {'再利用' if cached else '生成'}", flush=True)
            if output_format == 'mp3':
                encode_mp3(path, manifest['credit'], f"{profile['label']} {stem} {phrase['kanji']}")
            paths.append(path)
        segments = combine(paths, directory / "full.wav", profile["gap"])
        if output_format == 'mp3':
            encode_mp3(directory / 'full.wav', manifest['credit'], f"観音経 {profile['label']} 全{len(phrases)}句")
        prefix = f"assets/audio/generated/{digest}/{key}"
        manifest["profiles"][key] = {
            "label": profile["label"], "src": f"{prefix}/full.{output_format}",
            "gapSeconds": profile['gap'],
            "silenceTrim": dict(SILENCE_TRIM),
            "phrases": {str(p["id"]): {**segment, "kanji": p["kanji"], "yomi": p["yomi"],
                                        "src": f"{prefix}/{audio_stem(p)}.{output_format}"}
                        for p, segment in zip(reading, segments) if p['id'] != 'title'},
        }
        if title:
            manifest['profiles'][key]['title'] = {**title, **segments[0], 'src': f'{prefix}/title.{output_format}'}
    # Publish only when both profiles are complete. Earlier usable tracks remain on failure.
    atomic_write(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode())
    return manifest


def bounded_float(low, high):
    def parse(value):
        number = float(value)
        if not math.isfinite(number) or not low <= number <= high:
            raise argparse.ArgumentTypeError(f"{low}〜{high}の数値を指定してください。")
        return number
    return parse


def main(argv=None):
    parser = argparse.ArgumentParser(description="VOICEVOXで世尊偈のゆっくり音声と通し読みを自動生成")
    parser.add_argument("--engine", default="http://127.0.0.1:50021", help="VOICEVOXのローカルAPI URL")
    parser.add_argument("--list-speakers", action="store_true", help="使用可能な声・スタイルIDを表示")
    parser.add_argument("--speaker", type=int, help="声のスタイルID（一覧から選択）")
    parser.add_argument("--format", choices=['wav', 'mp3'], default='wav', help="出力形式。MP3にはffmpegが必要")
    parser.add_argument("--limit", type=int, help="試作する句数。省略時は結びまで全句を生成")
    parser.add_argument("--slow-speed", type=bounded_float(0.5, 2), default=0.7)
    parser.add_argument("--continuous-speed", type=bounded_float(0.5, 2), default=1.0)
    parser.add_argument("--slow-gap", type=bounded_float(0, 10), default=PROFILES['slow']['gap'], help="ゆっくり音声の句間（秒、省略時0）")
    parser.add_argument("--export-text", type=Path, help="読み原稿を保存して終了（VOICEVOX不要）")
    args = parser.parse_args(argv)
    url = urllib.parse.urlparse(args.engine)
    if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"} or url.username or url.password:
        parser.error("--engine は http://127.0.0.1:50021 のようなローカルURLを指定してください。")
    if args.limit is not None and args.limit < 1:
        parser.error('--limit は1以上で指定してください。')
    try:
        if args.export_text:
            phrases = read_phrases()
            if args.limit is not None and args.limit > len(phrases):
                parser.error(f'--limit は{len(phrases)}以下で指定してください。')
            phrases = phrases[:args.limit]
            title = read_title()
            reading = ([title] if title else []) + phrases
            atomic_write(args.export_text, ("\n".join(p["yomi"] for p in reading) + "\n").encode())
            print(f"読み原稿を保存しました: {args.export_text}（経本との照合が必要です）")
            return 0
        speakers = request(args.engine, "speakers", timeout=5)
        styles = [{"id": style["id"], "name": person["name"], "style": style["name"],
                   "uuid": person["speaker_uuid"]}
                  for person in speakers for style in person["styles"] if style.get("type", "talk") == "talk"]
        if args.list_speakers:
            for speaker in styles:
                print(f"{speaker['id']:>5}  {speaker['name']} / {speaker['style']}")
            return 0
        if args.speaker is None:
            parser.error("--list-speakers で声を確認し、--speaker ID を指定してください。")
        if args.format == 'mp3' and not shutil.which('ffmpeg'):
            parser.error('MP3の生成にはffmpegが必要です。')
        speaker = next((s for s in styles if s["id"] == args.speaker), None)
        if speaker is None:
            parser.error("指定したスタイルIDがありません。--list-speakers で確認してください。")
        phrases = read_phrases()
        if args.limit is not None and args.limit > len(phrases):
            parser.error(f'--limit は{len(phrases)}以下で指定してください。')
        phrases = phrases[:args.limit]
        version = request(args.engine, "version", timeout=5)
        print(f"{speaker['name']} / {speaker['style']}、{len(phrases)}句 × 2種類を生成します。")
        print("原稿の読み・選択した音声の利用条件は別途確認してください。")
        manifest = generate(phrases, speaker, version, args, ROOT / "assets/audio", title=read_title())
        print("完了。ページを再読み込みすると経本で音声を選べます。")
        print(f"クレジット: {manifest['credit']} / {speaker['style']}")
        return 0
    except (RuntimeError, ValueError, OSError, wave.Error, EOFError, SyntaxError, KeyError, TypeError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
