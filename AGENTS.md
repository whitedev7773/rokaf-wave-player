# ROKAF Wave Player — agent instructions

- Keep `index.html` self-contained: HTML, CSS and JavaScript must work without a build step.
- For MIDI `.mid`/`.midi` to Sequence DSL `.seq` conversion, **use** `.agents/skills/midi-to-seq-dsl/SKILL.md` and its `scripts/convert.py`; do not transcribe MIDI events by guessing.
- The DSL uses musical note-value denominators: `4` = one quarter-note beat, including standalone Delay lines. A trailing pull value `0` inherits the previous value.
- Preserve MIDI note onsets, offsets and chords; when notes overlap with different releases, allocate additional sequences rather than assuming pull resets.
- Use `python -m unittest discover -s .agents/skills/midi-to-seq-dsl/tests -v` to validate converter changes.
- Do not commit user MIDI, derived transcriptions, audio, or secrets unless the user expressly requests it and owns the rights.
