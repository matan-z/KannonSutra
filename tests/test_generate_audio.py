import argparse
from array import array
import importlib.util
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
import wave

SPEC = importlib.util.spec_from_file_location("generate_audio", Path(__file__).resolve().parents[1] / "scripts/generate_audio.py")
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


def pcm(seconds=0.1, rate=24000, voice=False):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        frames = array('h', (round(8000 * math.sin(2 * math.pi * 164 * i / rate))
                             for i in range(round(seconds * rate)))).tobytes() if voice else b"\0\0" * round(seconds * rate)
        output.writeframes(frames)
    return buffer.getvalue()


class GeneratorTests(unittest.TestCase):
    def test_optional_meaning_column(self):
        row = ['世尊妙相具', 'せ そん みょう そう ぐ', '美しいお姿をそなえた世尊よ']
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'sutra.js'
            source.write_text('const ROWS = [\n' + ',\n'.join(repr(row) for _ in range(104)) + '\n];', encoding='utf-8')
            self.assertEqual(generator.read_phrases(source)[0]['yomi'], 'せそんみょうそうぐ')

    def test_source_and_offline_export(self):
        phrases = generator.read_phrases()
        self.assertEqual(len(phrases), 119)
        self.assertEqual(phrases[0]["yomi"], "せそんみょうそうぐ")
        self.assertEqual(phrases[103]["kanji"], "是故応頂礼")
        self.assertEqual(phrases[104]['id'], 105)
        self.assertEqual(phrases[104]['kanji'], '爾時持地菩薩')
        self.assertEqual(phrases[-1]['part'], 'prose')
        self.assertEqual(phrases[-1]['kanji'], '阿耨多羅三藐三菩提心')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "reading.txt"
            self.assertEqual(generator.main(["--export-text", str(target), "--limit", "8"]), 0)
            self.assertEqual(len(target.read_text().splitlines()), 9)
            self.assertEqual(target.read_text().splitlines()[0], generator.read_title()['yomi'])
            self.assertEqual(generator.main(['--export-text', str(target)]), 0)
            self.assertEqual(len(target.read_text().splitlines()), len(phrases) + 1)
            self.assertEqual(target.read_text().splitlines()[-1], 'あのくたらさんみゃくさんぼだいしん')

    def test_title_is_separate_from_numbered_phrases(self):
        title = generator.read_title()
        self.assertEqual(title['id'], 'title')
        self.assertEqual(title['kanji'], '妙法蓮華経観世音菩薩普門品第二十五偈')
        self.assertEqual(title['yomi'], 'みょうほうれんげきょうかんぜおんぼさつふもんぼんだいにじゅうごげ')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'sutra.js'
            source.write_text('const ROWS = [];')
            self.assertIsNone(generator.read_title(source))
            source.write_text("export const SUTRA_TITLE = {\nkanji: '世尊', yomi: 'せ',\n};")
            with self.assertRaisesRegex(ValueError, '経題の漢字と読み'):
                generator.read_title(source)

    def test_optional_prose_has_variable_lengths_and_extra_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'sutra.js'
            source.write_text("const ROWS = [\n['世尊妙相具', 'せ そん みょう そう ぐ'],\n];\n"
                              "const PROSE_ROWS = [\n['世尊', 'せ そん', '世尊よ', 1],\n"
                              "['即従座起', 'そく じゅう ざ き', '立ち上がる', 1],\n];", encoding='utf-8')
            phrases = generator.read_phrases(source)
            self.assertEqual([p['id'] for p in phrases], [1, 2, 3])
            self.assertEqual([p['yomi'] for p in phrases], ['せそんみょうそうぐ', 'せそん', 'そくじゅうざき'])
            self.assertEqual([p['part'] for p in phrases], ['ge', 'prose', 'prose'])

    def test_sample_exact_offsets_and_silence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / "1.wav", root / "2.wav"]
            for path in paths:
                path.write_bytes(pcm())
            offsets = generator.combine(paths, root / "full.wav", 1.5)
            self.assertEqual(offsets, [{"start": 0, "end": 0.1}, {"start": 1.6, "end": 1.7}])
            _, _, count = generator.wav_info((root / "full.wav").read_bytes())
            self.assertEqual(count, 40800)

    def test_reject_truncated_wav(self):
        with self.assertRaises(ValueError):
            generator.wav_info(pcm()[:-20])

    def test_edge_silence_is_removed_but_internal_pause_and_speech_are_preserved(self):
        fmt, speech, _ = generator.wav_info(pcm(.2, voice=True))
        frames = b'\0\0' * 4800 + speech + b'\0\0' * 2400 + speech + b'\0\0' * 4800
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as output:
            output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            output.writeframes(frames)
        result = generator.trim_wav_silence(buffer.getvalue())
        trimmed_fmt, trimmed, count = generator.wav_info(result)
        self.assertEqual(trimmed_fmt, fmt)
        # Both spoken sections and their 100ms internal pause remain byte-exact.
        self.assertEqual(trimmed[240:-240], speech + b'\0\0' * 2400 + speech)
        self.assertEqual(count, 12240)
        self.assertEqual(generator.trim_wav_silence(result), result)

    def test_silent_phrase_is_not_published_after_trimming(self):
        with self.assertRaisesRegex(ValueError, '無音'):
            generator.trim_wav_silence(pcm())

    def test_resume_and_preserve_published_manifest_on_failure(self):
        phrases = generator.read_phrases()[:2]
        speaker = {"id": 99, "name": "テスト話者", "style": "ノーマル", "uuid": "test"}
        args = argparse.Namespace(engine="http://127.0.0.1:50021", slow_speed=0.7, slow_gap=1.5, continuous_speed=1.0)
        calls = []

        def api(base, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            return pcm(voice=True) if endpoint == "synthesis" else {}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = generator.generate(phrases, speaker, "test", args, root, api)
            self.assertEqual(set(manifest["profiles"]), {"slow", "continuous"})
            self.assertEqual(len([c for c in calls if c[0] == "synthesis"]), 4)
            speeds = [c[1]["payload"]["speedScale"] for c in calls if c[0] == "synthesis"]
            self.assertEqual(speeds, [0.7, 0.7, 1.0, 1.0])
            entries = list(manifest['profiles']['continuous']['phrases'].values())
            self.assertEqual(entries[0]['end'], entries[1]['start'])
            calls.clear()
            generator.generate(phrases, speaker, "test", args, root, api)
            self.assertEqual(calls, [])
            published = (root / "manifest.json").read_bytes()

            def failed_api(*a, **kw):
                raise RuntimeError("engine stopped")

            args.slow_speed = 0.6
            with self.assertRaises(RuntimeError):
                generator.generate(phrases, speaker, "test", args, root, failed_api)
            self.assertEqual((root / "manifest.json").read_bytes(), published)
            self.assertEqual(json.loads(published)["credit"], "VOICEVOX:テスト話者")


if __name__ == "__main__":
    unittest.main()
