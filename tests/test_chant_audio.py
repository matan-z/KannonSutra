import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if any(importlib.util.find_spec(name) is None for name in ['numpy','scipy','soundfile']):
    raise unittest.SkipTest('音声調整用ライブラリが未インストールです。')

import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chant_audio as chant
from generate_audio import read_phrases,read_title


class ChantTests(unittest.TestCase):
    def test_long_vowels_are_sustained_instead_of_foreign_sounding_diphthongs(self):
        for text,lyric in [('とう','ト'),('ほう','ホ'),('そう','ソ'),('みょう','ミョ'),('しゅう','シュ'),('れい','レ')]:
            self.assertEqual(chant.kanji_moras(text),[{'lyric':lyric,'weight':2.}])
        self.assertEqual([m['lyric'] for m in chant.kanji_moras('がい')],['ガ','イ'])
        self.assertEqual([m['lyric'] for m in chant.kanji_moras('ぶっ')],['ブ','ッ'])

    def test_one_kanji_per_reference_beat_and_no_silence_between_phrases(self):
        items=[{'id':1,'yomiUnits':['せ','そん','みょう','そう','ぐ']},
               {'id':2,'yomiUnits':['かく','しゅう','とう','か','がい']}]
        score=chant.make_score(items)
        notes=score['notes']
        self.assertEqual(notes[0]['lyric'],'')
        self.assertEqual(notes[-1]['lyric'],'')
        self.assertTrue(all(n['lyric'] for n in notes[1:-1]))
        self.assertEqual(sum(n['frame_length'] for n in notes[1:-1]),625)
        self.assertEqual([n['lyric'] for n in notes if n['id'].startswith('2:2:')],['ト'])
        # Adjacent kanji must not be merged merely because they form a long vowel.
        adjacent=chant.make_score([{'id':1,'yomiUnits':['こ','う']}])
        self.assertEqual([n['lyric'] for n in adjacent['notes'][1:-1]],['コ','ウ'])

    def test_slow_reading_changes_tempo_without_transposing_pitch(self):
        items=[{'id':1,'yomiUnits':['せ','そん','みょう','そう','ぐ']}]
        fast=chant.make_score(items,1.)['notes'][1:-1]
        slow=chant.make_score(items,.7)['notes'][1:-1]
        self.assertGreater(sum(n['frame_length'] for n in slow),sum(n['frame_length'] for n in fast)*1.4)
        self.assertEqual([n['key'] for n in fast],[n['key'] for n in slow])

    def test_source_preserves_character_readings_and_existing_phrase_ids(self):
        items=[read_title(with_units=True)]+read_phrases(with_units=True)
        self.assertEqual(len(items),120)
        self.assertEqual(items[0]['id'],'title')
        self.assertEqual(items[-1]['id'],119)
        self.assertEqual(sum(len(p['yomiUnits']) for p in items),616)
        for p in items:
            self.assertEqual(len(p['kanji']),len(p['yomiUnits']))
            self.assertEqual(p['yomi'],''.join(p['yomiUnits']))
            chant.make_score([p])

    def test_reference_curve_retains_natural_pitch_changes(self):
        times=np.arange(0,60,.01)
        f0=163+5*np.sin(times*2)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ref.npz'
            np.savez(path,times=times,f0=f0)
            t,hz,median=chant.reference_pitch(path)
            self.assertGreater(np.ptp(hz),8)
            self.assertAlmostEqual(median,163,delta=1)

    def test_frame_decoder_uses_reference_contour_and_phoneme_boundaries(self):
        items=[{'id':1,'yomiUnits':['せ']},{'id':2,'yomiUnits':['そん']}]
        score=chant.make_score(items)
        phonemes=[{'phoneme':'pau' if n['key'] is None else 'a',
                   'frame_length':n['frame_length'],'note_id':n['id']} for n in score['notes']]
        f0=[hz for n in score['notes'] for hz in [0. if n['key'] is None else 164.]*n['frame_length']]
        query={'phonemes':phonemes,'f0':f0,'volume':[1.]*len(f0)}
        count=len(f0)*256
        buffer=io.BytesIO()
        sf.write(buffer,.1*np.sin(2*np.pi*164*np.arange(count)/24000),24000,format='WAV',subtype='PCM_16')

        def api(engine,endpoint,**kwargs):
            if endpoint=='sing_frame_audio_query':return query
            return buffer.getvalue()

        with patch.object(chant,'request',side_effect=api):
            clips,rendered=chant.render_block(items,'local',3053,(np.array([0.,100.]),np.array([150.,175.]),163.))
        self.assertEqual(len(clips),2)
        self.assertEqual(sum(map(len,clips)),(len(f0)-30)*256)
        revised=np.array(rendered['f0'])
        self.assertTrue(np.all(revised[:15]==0))
        self.assertGreater(np.ptp(revised[revised>0]),.1)


if __name__=='__main__':
    unittest.main()
