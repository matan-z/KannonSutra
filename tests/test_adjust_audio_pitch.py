import importlib.util
import argparse
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if any(importlib.util.find_spec(name) is None for name in ['numpy', 'scipy', 'soundfile', 'pyworld']):
    raise unittest.SkipTest('音程調整用の追加ライブラリが未インストールです。')

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import adjust_audio_pitch as pitch


class PitchTests(unittest.TestCase):
    def test_pitch_changes_without_changing_duration_or_clipping(self):
        sr = 24000
        times = np.arange(sr * 2) / sr
        source = .18 * np.sin(2 * np.pi * 120 * times)
        result = pitch.retune(source, sr, np.array([0., 1.]), np.array([164., 164.]), 0, 1)
        measured, _ = pitch.extract_pitch(result, sr)
        self.assertEqual(len(result), len(source))
        self.assertLess(np.max(np.abs(result)), .94)
        self.assertGreater(np.sqrt(np.mean(result * result)), .05)
        self.assertAlmostEqual(float(np.median(measured[measured > 0])), 164., delta=5.)

    def test_reference_requires_valid_time_range(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reference.wav'
            sf.write(path, np.zeros(24000), 24000)
            with self.assertRaisesRegex(ValueError, '解析範囲'):
                pitch.reference_curve(path, 2, 3)

    def test_silence_is_not_published_as_tuned_speech(self):
        with self.assertRaisesRegex(ValueError, '音程を検出'):
            pitch.retune(np.zeros(24000), 24000, np.array([0., 1.]), np.array([164., 164.]), 0, 1)

    def test_new_title_and_prose_reuse_existing_tuned_body_audio(self):
        sr = 24000
        tone = .18 * np.sin(2 * np.pi * 164 * np.arange(sr) / sr)
        buffer = io.BytesIO()
        sf.write(buffer, tone, sr, format='WAV', subtype='PCM_16')
        wav = buffer.getvalue()
        phrases = [
            {'id': 1, 'part': 'ge', 'kanji': '世尊', 'yomi': 'せそん'},
            {'id': 2, 'part': 'prose', 'kanji': '仏説是普門品時', 'yomi': 'ぶっせつぜふもんぼんじ'},
        ]
        metadata = {'url': pitch.REFERENCE_URL, 'startSeconds': 40., 'endSeconds': 370.,
                    'medianHz': 164., 'pitchRangeHz': [160., 168.]}
        generated_texts = []

        def api(base, endpoint, **kwargs):
            if endpoint == 'speakers':
                return [{'name': 'テスト', 'styles': [{'id': 53, 'name': 'ノーマル'}]}]
            if endpoint == 'audio_query':
                generated_texts.append(kwargs['params']['text'])
                return {}
            if endpoint == 'synthesis':
                return wav
            raise AssertionError(endpoint)

        def encode(source, credit, title):
            target = source.with_suffix('.mp3')
            target.write_bytes(b'test-only-encoded-audio')
            return target

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'js/data').mkdir(parents=True)
            (root/'js/data/sekai-ge.js').write_text("export const SUTRA_TITLE = {\nkanji: '経題', yomi: 'きょう だい',\n};")
            original = {'version': 1, 'credit': 'VOICEVOX:テスト', 'style': 'ノーマル',
                        'pitchReference': metadata, 'profiles': {}}
            for mode in ['slow', 'continuous']:
                folder = root / 'assets/audio/old' / mode
                folder.mkdir(parents=True)
                (folder/'001.wav').write_bytes(wav)
                (folder/'001.mp3').write_bytes(b'original-' + mode.encode())
                original['profiles'][mode] = {'label': mode, 'src': 'unused.mp3', 'phrases': {
                    '1': {**phrases[0], 'start': 0., 'end': 1., 'src': f'assets/audio/old/{mode}/001.mp3'},
                }}
            manifest_path = root/'assets/audio/manifest.json'
            manifest_path.write_text(json.dumps(original))
            reference = root/'reference.wav'
            reference.write_bytes(wav)
            args = argparse.Namespace(reference=reference, start=40., end=370., engine='http://127.0.0.1:50021')
            with patch.object(pitch, 'ROOT', root), patch.object(pitch, 'read_phrases', return_value=phrases), \
                 patch.object(pitch, 'reference_curve', return_value=(np.array([0., 1.]), np.array([164., 164.]), metadata)), \
                 patch.object(pitch, 'request', side_effect=api), patch.object(pitch, 'encode_mp3', side_effect=encode):
                revised = pitch.process(args)
            self.assertEqual(generated_texts, ['きょうだい', phrases[1]['yomi']] * 2)
            self.assertEqual(revised['phraseCount'], 2)
            self.assertEqual(revised['partCounts'], {'ge': 1, 'prose': 1})
            for mode in ['slow', 'continuous']:
                entries = revised['profiles'][mode]['phrases']
                self.assertEqual(set(entries), {'1', '2'})
                self.assertEqual((root/entries['1']['src']).read_bytes(), b'original-' + mode.encode())
                self.assertEqual((root/entries['1']['src']).with_suffix('.wav').read_bytes(), wav)
                self.assertEqual(entries['2']['kanji'], '仏説是普門品時')
                title = revised['profiles'][mode]['title']
                self.assertEqual(title['kanji'], '経題')
                self.assertEqual(title['start'], 0)
                self.assertEqual(title['end'], entries['1']['start'])
                self.assertEqual(entries['1']['end'], entries['2']['start'])
            self.assertEqual(json.loads(manifest_path.read_text())['phraseCount'], 2)


if __name__ == '__main__':
    unittest.main()
