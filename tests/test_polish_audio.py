import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if any(importlib.util.find_spec(name) is None for name in ['numpy', 'scipy', 'soundfile']):
    raise unittest.SkipTest('音声調整用ライブラリが未インストールです。')

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import polish_audio as polish


class PolishTests(unittest.TestCase):
    def test_thumps_are_reduced_and_pitch_timing_preserved(self):
        sr = 24000
        time = np.arange(sr) / sr
        voice = .15 * np.sin(2 * np.pi * 164 * time)
        source = voice + .15 * np.sin(2 * np.pi * 25 * time)
        result = polish.clean_edges(source, sr)
        self.assertEqual(len(result), len(source))
        self.assertEqual(result[0], 0)
        self.assertEqual(result[-1], 0)

        def amplitude(x, hz):
            return abs(np.dot(x[1000:-1000], np.exp(-2j * np.pi * hz * time[1000:-1000])))

        self.assertLess(amplitude(result, 25), amplitude(source, 25) * .05)
        self.assertAlmostEqual(amplitude(result, 164) / amplitude(source, 164), 1, delta=.05)

    def test_short_click_is_removed_without_shifting_voice(self):
        sr = 24000
        time = np.arange(sr) / sr
        voice = .15 * np.sin(2 * np.pi * 164 * time)
        source = voice.copy()
        source[sr // 2] += .8
        result = polish.declick(source, sr)
        self.assertEqual(len(result), len(source))
        self.assertLess(np.max(np.abs(result[sr//2-20:sr//2+20] - voice[sr//2-20:sr//2+20])), .08)
        self.assertGreater(np.corrcoef(result[1000:10000], voice[1000:10000])[0, 1], .99)

    def test_reverb_has_audible_tail_without_clipping_or_pre_echo(self):
        sr = 24000
        voice = .2 * np.sin(2 * np.pi * 164 * np.arange(sr // 2) / sr)
        source = np.concatenate([np.zeros(sr // 10), voice])
        result = polish.reverberate(source, sr)
        self.assertEqual(len(result), len(source) + round(.85 * sr))
        self.assertLessEqual(np.max(np.abs(result)), .890001)
        self.assertLess(np.max(np.abs(result[:sr//10])), 1e-10)
        self.assertGreater(polish.rms(result[len(source):len(source)+sr//10]), .005)
        self.assertAlmostEqual(polish.rms(result[:len(source)]), polish.rms(source), delta=.001)
        np.testing.assert_array_equal(result, polish.reverberate(source, sr))

    def test_native_pitch_preserves_unvoiced_consonants_and_sets_reference_pitch(self):
        sr = 24000
        voice = .2 * np.sin(2 * np.pi * 164 * np.arange(sr) / sr)
        buffer = io.BytesIO()
        sf.write(buffer, voice, sr, format='WAV', subtype='PCM_16')
        seen = []

        def api(base, endpoint, **kwargs):
            if endpoint == 'audio_query':
                return {'accent_phrases': [{'moras': [{'pitch': 4.5}, {'pitch': 0.}, {'pitch': 5.2}]}]}
            seen.append(kwargs['payload'])
            return buffer.getvalue()

        with patch.object(polish, 'request', side_effect=api):
            polish.synthesize_native({'yomi': 'かくしゅうとうかがい'}, 'slow', 53, 'http://127.0.0.1:50021', 163.574)
        pitches = [m['pitch'] for m in seen[0]['accent_phrases'][0]['moras']]
        self.assertEqual(pitches, [math.log(163.574), 0., math.log(163.574)])
        self.assertEqual(seen[0]['speedScale'], .7)
        self.assertEqual(seen[0]['pitchScale'], 0)

    def test_invalid_audio_is_rejected(self):
        with self.assertRaises(ValueError):
            polish.clean_edges(np.zeros(24000), 24000)

    def test_rebuilt_offsets_tail_and_reprocessing_without_double_echo(self):
        sr = 24000
        buffer = io.BytesIO()
        sf.write(buffer, .15 * np.sin(2 * np.pi * 164 * np.arange(sr // 10) / sr),
                 sr, format='WAV', subtype='PCM_16')

        def encode(source, credit, title):
            source.with_suffix('.mp3').write_bytes(b'test-only-mp3')

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'js/data').mkdir(parents=True)
            (root/'js/data/sekai-ge.js').write_text(
                "const ROWS = [\n['世尊','せ そん'],\n['如来','にょ らい'],\n];\n"
                "export const SUTRA_TITLE = {\nkanji: '経題', yomi: 'きょう だい',\n};")
            audio = root/'assets/audio'
            audio.mkdir(parents=True)
            title = {'kanji': '経題', 'yomi': 'きょうだい', 'start': 0, 'end': .2, 'src': 'old.mp3'}
            phrases = {'1': {'kanji': '世尊', 'yomi': 'せそん', 'start': .2, 'end': .4, 'src': 'old.mp3'},
                       '2': {'kanji': '如来', 'yomi': 'にょらい', 'start': .4, 'end': .6, 'src': 'old.mp3'}}
            manifest = {'credit': 'VOICEVOX:テスト', 'style': 'ノーマル', 'pitchReference': {'medianHz': 164},
                        'profiles': {mode: {'label': mode, 'src': 'old.mp3', 'title': title, 'phrases': phrases}
                                     for mode in ['slow', 'continuous']}}
            (audio/'manifest.json').write_text(json.dumps(manifest))
            speakers = [{'name': 'テスト', 'styles': [{'id': 53, 'name': 'ノーマル'}]}]
            with patch.object(polish, 'request', return_value=speakers), \
                 patch.object(polish, 'synthesize_native', return_value=buffer.getvalue()), \
                 patch.object(polish, 'encode_mp3', side_effect=encode):
                first = polish.process(root, native_pitch=True)
            original_audio = {}
            for mode, profile in first['profiles'].items():
                self.assertAlmostEqual(profile['title']['end'], .1)
                self.assertAlmostEqual(profile['phrases']['1']['start'], .1)
                self.assertAlmostEqual(profile['phrases']['2']['end'], .3)
                self.assertAlmostEqual(profile['speechEndSeconds'], .3)
                self.assertAlmostEqual(profile['durationSeconds'], 1.15)
                original_audio[mode] = (root/profile['src']).with_suffix('.wav').read_bytes()
            with patch.object(polish, 'encode_mp3', side_effect=encode):
                second = polish.process(root)
            for mode, profile in second['profiles'].items():
                self.assertEqual(original_audio[mode], (root/profile['src']).with_suffix('.wav').read_bytes())
            # A newly rendered chant draft can be mastered before any public switch.
            published=(audio/'manifest.json').read_bytes()
            draft=json.loads(published)
            draft['notice']='draft chant'
            with patch.object(polish,'encode_mp3',side_effect=encode):
                third=polish.process(root,manifest_override=draft)
            self.assertEqual(third['notice'],'draft chant')
            digest=Path(third['profiles']['slow']['src']).parts[3]
            self.assertEqual((audio/f'manifest-before-polish-{digest}.json').read_bytes(),published)


if __name__ == '__main__':
    unittest.main()
