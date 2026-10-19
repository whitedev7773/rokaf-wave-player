import sys
import tempfile
import unittest
from pathlib import Path
from fractions import Fraction

import mido

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from convert import extract_midi, prepare_events, allocate_voices, make_dsl, TimeMap, quantize, numeric


def synth(path, *, overlap=False, tempo=False, signature=False):
    midi = mido.MidiFile(ticks_per_beat=480)
    t1 = mido.MidiTrack()
    midi.tracks.append(t1)
    t1.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    if signature:
        t1.append(mido.MetaMessage("time_signature", numerator=3, denominator=4, time=0))
    t1.append(mido.Message("note_on", note=60, velocity=90, channel=0, time=0))
    t1.append(mido.Message("note_on", note=64, velocity=80, channel=0, time=0))
    if overlap:
        t1.append(mido.Message("note_on", note=67, velocity=60, channel=0, time=240))
        t1.append(mido.Message("note_off", note=60, velocity=0, channel=0, time=240))
        t1.append(mido.Message("note_off", note=64, velocity=0, channel=0, time=0))
        t1.append(mido.Message("note_off", note=67, velocity=0, channel=0, time=240))
    else:
        t1.append(mido.Message("note_off", note=60, velocity=0, channel=0, time=480))
        t1.append(mido.Message("note_off", note=64, velocity=0, channel=0, time=0))
    if tempo:
        t1.append(mido.MetaMessage("set_tempo", tempo=1000000, time=0))
        t1.append(mido.Message("note_on", note=72, velocity=90, channel=0, time=0))
        t1.append(mido.Message("note_off", note=72, velocity=0, channel=0, time=480))
    midi.save(path)


class MidiDslTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.mid"

    def tearDown(self):
        self.tmp.cleanup()

    def test_quarter_note_and_chord(self):
        synth(self.path)
        data = extract_midi(self.path)
        dsl, stats = make_dsl(data, mode="precise", input_name=self.path.name)
        self.assertIn("c4 e4 4 0", dsl)
        self.assertEqual(stats["note_count"], 2)
        self.assertEqual(stats["play_events"], 1)
        self.assertEqual(stats["sequence_count"], 1)

    def test_overlap_creates_additional_voice(self):
        synth(self.path, overlap=True)
        data = extract_midi(self.path)
        dsl, stats = make_dsl(data)
        self.assertEqual(stats["sequence_count"], 2)
        self.assertIn("c4 e4 4 0", dsl)
        self.assertIn("g4 4 0", dsl)
        self.assertIn("8\ng4", dsl)  # starts half a beat after the first chord

    def test_tempo_map_flattens_changes(self):
        synth(self.path, tempo=True)
        data = extract_midi(self.path)
        self.assertEqual(data.time_map.beat(480), Fraction(1))
        self.assertEqual(data.time_map.beat(960), Fraction(3))
        dsl, stats = make_dsl(data)
        self.assertIn("c5 2 0", dsl)
        self.assertEqual(stats["tempo_changes"], 1)

    def test_time_signature_comments(self):
        synth(self.path, signature=True)
        data = extract_midi(self.path)
        dsl, stats = make_dsl(data)
        self.assertIn("$ 001마디 (3/4)", dsl)
        self.assertEqual(stats["measure_count"], 1)

    def test_grid_rounding(self):
        self.assertEqual(quantize(Fraction(49, 100), Fraction(1, 4)), Fraction(1, 2))
        self.assertEqual(numeric(Fraction(48, 5)), "9.6")

    def test_rest_denominator(self):
        synth(self.path)
        data = extract_midi(self.path)
        self.assertEqual(data.time_map.beat(240), Fraction(1, 2))


if __name__ == "__main__":
    unittest.main()
