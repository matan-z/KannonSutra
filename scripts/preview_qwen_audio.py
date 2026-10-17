#!/usr/bin/env python3
"""Generate a short, separate Qwen voice-design audition; never publish it.

The existing application manifest and complete recordings are not modified.
Naturalness and sutra pronunciation still require a human listening review.
"""
import argparse
import importlib.metadata
import json
import time
from pathlib import Path

from generate_audio import ROOT, atomic_write, encode_mp3, read_phrases

MODEL = 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'
DESCRIPTION = (
    'A native Japanese middle-aged male Buddhist monk, with a warm resonant '
    'baritone voice. Recite a Japanese Buddhist sutra in a calm, steady, flowing '
    'traditional chanting style. Clear connected Japanese pronunciation, '
    'gently sustained vowels and restrained pitch movement. Keep the phrases '
    'connected with short breaths. Recorded close to the microphone in a quiet '
    'room, without music.'
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default=MODEL)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--max-new-tokens', type=int, default=512)
    parser.add_argument('--seed', type=int, default=20261017)
    parser.add_argument('--case', choices=['ordinary', 'sutra'], default='sutra')
    parser.add_argument('--output', type=Path,
                        default=Path('/tmp/kannongyo-qwen-diagnostics/reading'))
    args = parser.parse_args()

    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel
    from polish_audio import reverberate

    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    phrases = read_phrases()[:4]
    # Kana fixes the uncommon Buddhist readings; no spaces inside a phrase.
    text = '、'.join(p['yomi'] for p in phrases) + '。'
    instruction = DESCRIPTION
    if args.case == 'ordinary':
        text = '今日はいい天気です。'
        instruction = '落ち着いた中年男性の声。自然で明瞭な日本語で話してください。'
    print(f'Loading {args.model} on CPU (float32, without custom quantization)', flush=True)
    started = time.monotonic()
    model = Qwen3TTSModel.from_pretrained(
        args.model, device_map='cpu', dtype=torch.float32,
        attn_implementation='eager', low_cpu_mem_usage=True,
    )
    completion = {}
    original_generate = model.model.talker.generate

    def observe_completion(*positional, **keyword):
        result = original_generate(*positional, **keyword)
        eos = model.model.config.talker_config.codec_eos_token_id
        completion['endedWithEos'] = bool((result.sequences[:, -1] == eos).all())
        completion['sequenceLength'] = result.sequences.shape[-1]
        return result

    model.model.talker.generate = observe_completion
    print(f'Model loaded after {time.monotonic()-started:.1f}s; generating: {text}', flush=True)
    with torch.inference_mode():
        wavs, sr = model.generate_voice_design(
            text=text, language='Japanese', instruct=instruction,
            max_new_tokens=args.max_new_tokens,
        )
    samples = np.asarray(wavs[0])
    if samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all():
        raise ValueError('The model returned invalid audio.')
    if not completion.get('endedWithEos'):
        raise RuntimeError('生成が終了トークンに到達しませんでした。途中の音声は試聴ファイルに出力しません。')
    # Keep the engine output free of pitch processing while judging pronunciation.
    peak = float(np.max(np.abs(samples)))
    if peak > .95:
        samples = samples * (.95 / peak)
    hop = model.model.speech_tokenizer.get_decode_upsample_rate()
    possibly_capped = len(samples) >= (args.max_new_tokens - 2) * hop
    if possibly_capped:
        print('Warning: token limit reached; this is an excerpt, not a complete reading.', flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    wav_path = args.output.with_suffix('.wav')
    sf.write(wav_path, samples, sr, subtype='PCM_16')
    encode_mp3(wav_path, 'Qwen3-TTS synthetic voice', '観音経 新エンジン試聴・冒頭四句')
    audition = samples.copy()
    fade_out = .3 if possibly_capped else .008
    n = min(len(audition), round(fade_out * sr))
    audition[-n:] *= np.cos(np.linspace(0, np.pi / 2, n)) ** 2
    n = min(len(audition), round(.008 * sr))
    audition[:n] *= np.sin(np.linspace(0, np.pi / 2, n)) ** 2
    wet = reverberate(audition, sr)
    echo_path = wav_path.with_name(wav_path.stem + '-echo.wav')
    sf.write(echo_path, wet, sr, subtype='PCM_16')
    encode_mp3(echo_path, 'Qwen3-TTS synthetic voice', '観音経 新エンジン試聴・残響付き')
    local_revision = Path(args.model) / 'download-revision.json'
    revision = json.loads(local_revision.read_text()).get('revision') if local_revision.exists() else None
    atomic_write(args.output.with_suffix('.json'), json.dumps({
        'model': args.model, 'qwenTtsVersion': importlib.metadata.version('qwen-tts'),
        'text': text, 'kanji': [p['kanji'] for p in phrases],
        'instruction': instruction, 'seed': args.seed, 'case': args.case,
        'cpuInt8': False, 'completion': completion,
        'maxNewTokens': args.max_new_tokens,
        'possiblyReachedTokenLimit': possibly_capped,
        'modelSource': MODEL,
        'revision': revision,
        'durationSeconds': len(samples) / sr, 'sampleRate': sr,
        'echoFile': str(echo_path.with_suffix('.mp3')),
        'echoDurationSeconds': len(wet) / sr, 'fadeOutSeconds': fade_out,
        'elapsedSeconds': time.monotonic() - started,
        'listeningReview': 'pending; not published to the application',
    }, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Saved {wav_path.with_suffix(".mp3")} ({len(samples)/sr:.2f}s)', flush=True)


if __name__ == '__main__':
    main()
