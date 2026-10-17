from array import array
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import tighten_continuous_audio as timing
from generate_audio import wav_info


class TimingTests(unittest.TestCase):
    def test_selected_profile_is_trimmed_without_changing_speech_or_other_profile(self):
        rate = 24000
        speech = array('h', (round(8000 * math.sin(2 * math.pi * 164 * i / rate))
                             for i in range(2400))).tobytes()
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as output:
            output.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            output.writeframes(b'\0\0' * 2400 + speech + b'\0\0' * 2400)
        for mode in ['slow', 'continuous']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'js/data').mkdir(parents=True)
                (root / 'js/data/sekai-ge.js').write_text(
                    "const ROWS = [\n['世尊', 'せ そん'],\n['如来', 'にょ らい'],\n];\n"
                    "export const SUTRA_TITLE = {\nkanji: '経題', yomi: 'きょう だい',\n};")
                audio = root / 'assets/audio'
                audio.mkdir(parents=True)
                (audio / 'old.wav').write_bytes(buffer.getvalue())
                entries = {str(i): {'kanji': k, 'yomi': y, 'start': (i-1)*1.8,
                                   'end': (i-1)*1.8+.3, 'src': 'assets/audio/old.mp3'}
                           for i, k, y in [(1, '世尊', 'せそん'), (2, '如来', 'にょらい')]}
                original = {'credit': 'VOICEVOX:テスト', 'profiles': {
                    key: {'label': key, 'src': 'assets/audio/old.mp3', 'phrases': entries,
                          'title': {'kanji': '経題', 'yomi': 'きょうだい', 'start': 0, 'end': .3, 'src': 'assets/audio/old.mp3'}}
                    for key in ['slow', 'continuous']}}
                manifest = audio / 'manifest.json'
                manifest.write_text(json.dumps(original))
                before = manifest.read_bytes()

                def encode(source, credit, title):
                    source.with_suffix('.mp3').write_bytes(b'test-only-mp3')

                # Encoding failure must leave the published track intact.
                with patch.object(timing, 'encode_mp3', side_effect=RuntimeError('encode failed')):
                    with self.assertRaises(RuntimeError):
                        timing.process(root, mode)
                self.assertEqual(manifest.read_bytes(), before)
                with patch.object(timing, 'encode_mp3', side_effect=encode):
                    revised = timing.process(root, mode)
                other = 'continuous' if mode == 'slow' else 'slow'
                self.assertEqual(revised['profiles'][other], original['profiles'][other])
                profile = revised['profiles'][mode]
                self.assertEqual(profile['gapSeconds'], 0)
                first, second = profile['phrases'].values()
                self.assertEqual(profile['title']['end'], first['start'])
                self.assertAlmostEqual(first['start'], .11)
                self.assertEqual(first['end'], second['start'])
                self.assertAlmostEqual(second['end'], .33)
                _, frames, _ = wav_info((root / first['src']).with_suffix('.wav').read_bytes())
                self.assertEqual(frames[240:-240], speech)
                _, full, _ = wav_info((root / profile['src']).with_suffix('.wav').read_bytes())
                self.assertEqual(full, frames * 3)
                self.assertEqual((audio / f'kannongyo-complete-{mode}.mp3').read_bytes(), b'test-only-mp3')


if __name__ == '__main__':
    unittest.main()
