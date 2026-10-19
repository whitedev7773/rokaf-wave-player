---
name: midi-to-seq-dsl
description: Convert attached Standard MIDI (.mid/.midi) files into the user's custom text music sequencer DSL (.seq), preserving notes, chords, timing, tempo and time-signature bar markers. Use whenever the user asks to turn MIDI into Sequence Player code, arrange a MIDI as measure-separated text score, or create precise/readable DSL notation from MIDI.
---

# MIDI → Sequence DSL

Convert uploaded MIDI to the user's custom text-based synthesizer/sequencer code. **Always run the bundled converter** rather than guessing notes or copying file contents. Keep the original `.mid` unchanged.

## Workflow

1. Locate the user's `.mid` or `.midi` file; when several are present, select the one specified by the user. Do not substitute a similarly named song found online.
2. Read [references/syntax.md](references/syntax.md) when interpreting DSL semantics or discussing limitations.
3. Install converter dependency if necessary: `python -m pip install -r requirements.txt` (only if the environment permits).
4. Convert with `python scripts/convert.py INPUT.mid -o OUTPUT.seq --mode precise`.
5. By default include measure headings (`$ 001마디 (4/4)`) and preserve precise MIDI onsets/releases. If the user requests easier editing, additionally create a readable 1/16-grid version using `--mode readable`.
6. Review the script's warnings and report any information not representable in DSL (e.g., velocity or sustain pedal). Do not claim waveform/timbre equivalence to MIDI.
7. Deliver a downloadable `.seq` file with the note, event, sequence and measure counts. For a file-producing environment, save the final file using its file persistence mechanism.

## Command examples

```bash
python scripts/convert.py "music.mid" --mode precise -o "music_precise.seq"
python scripts/convert.py "music.mid" --mode readable --grid 16 -o "music_readable.seq"
python scripts/convert.py "music.mid" --no-measures --no-timbre -o "music_plain.seq"
python scripts/convert.py "music.mid" --json -o "music.seq"
```

## Essential conversion rules

- `4` is one quarter note (1 beat), **not four beats**. A single `4` line delays one quarter note. For a duration of `b` quarter-note beats, write the note-value denominator `4/b`, including decimals as needed.
- Polyphonic notes with identical start **and** end are a single chord: `c4 e4 g4 4 0`. Different lengths or partially overlapping notes require **separate** `- Seq N` streams to preserve their timing exactly.
- Use `0` for every note's pull/overlap field and allocate voices with no overlapping events within a stream. `0` inherits the previous pull; no nonzero pull is emitted, avoiding unspecified pull-reset behavior (assuming initial pull is 0).
- Delay commands are standalone positive decimal denominators; inline comments start with `$`. The comments marking measures do not change playback.
- Preserve global MIDI time when tempo changes occur by flattening note time into an equivalent fixed `*bpm` timebase for each generated sequence.
- Chords have unlimited pitches. `MIDI 60 → c4` by default, configurable via `--middle-c`.
- Velocity, MIDI soundbanks/programs, continuous controllers, pedal, pitch bends and percussion timbres cannot be faithfully expressed in known DSL syntax. Synth `~sin`/`!a...` values are approximations only.
- A readable grid quantizes event start **and** end times, which intentionally changes timing. Use precise output when timing fidelity matters.
- If a MIDI is invalid (unpaired note_on, type 2, SMPTE timing), report the limitation rather than inventing data.

## Resources

- Converter: `scripts/convert.py`
- DSL semantics, caveats, and numeric examples: `references/syntax.md`
- Automated regression tests: `tests/test_convert.py`
