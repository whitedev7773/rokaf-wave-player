#!/usr/bin/env python3
"""Convert Standard MIDI files to the user's text Sequence DSL.

Dependency: mido (pip install -r requirements.txt)
Exact-mode note events are preserved by splitting overlapping groups into voices.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
from fractions import Fraction
from heapq import heappop, heappush
from pathlib import Path
from typing import Iterable
import json
import re
import sys

try:
    import mido
except ImportError:
    sys.exit("mido가 필요합니다: python -m pip install mido")

NAMES = ("c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b")
TIMBRE = "~sin1:1 +sin2:0.22 +sin3:0.11 +sin4:0.055 +sin5:0.025 +sin6:0.012"
ADSR = "!a5 !d650 !s25 !r85"


@dataclass(frozen=True)
class Note:
    start: int
    end: int
    pitch: int
    channel: int
    velocity: int


@dataclass(frozen=True)
class Event:
    start: Fraction
    end: Fraction
    pitches: tuple[int, ...]


class TimeMap:
    """Return score-quarter units measured at a single fixed output tempo.

    Tick-to-time mapping integrates all MIDI set_tempo events. The returned
    quarter units follow actual seconds, so a DSL with a single *bpm value can
    preserve every note onset and release even with tempo changes.
    """
    def __init__(self, ticks_per_beat: int, tempo_changes: list[tuple[int, int]]):
        self.ppq = ticks_per_beat
        changes_by_tick = {0: 500000}
        for tick, tempo in tempo_changes:
            changes_by_tick[tick] = tempo
        self.ticks = sorted(changes_by_tick)
        self.tempos = [changes_by_tick[t] for t in self.ticks]
        self.base_tempo = self.tempos[0]
        self.cumulative_us: list[Fraction] = [Fraction(0)]
        for i in range(1, len(self.ticks)):
            dt = self.ticks[i] - self.ticks[i - 1]
            self.cumulative_us.append(
                self.cumulative_us[-1] + Fraction(dt * self.tempos[i - 1], self.ppq)
            )

    def beat(self, tick: int | Fraction) -> Fraction:
        idx = max(0, bisect_right(self.ticks, tick) - 1)
        microseconds = (self.cumulative_us[idx]
                        + Fraction((tick - self.ticks[idx]) * self.tempos[idx], self.ppq))
        return microseconds / self.base_tempo

    @property
    def bpm(self) -> float:
        return 60000000 / self.base_tempo


@dataclass
class MidiData:
    midi: mido.MidiFile
    tracks: list[list[Note]]
    time_map: TimeMap
    signatures: list[tuple[int, int, int]]
    warnings: list[str]
    end_tick: int


def extract_midi(path: Path) -> MidiData:
    midi = mido.MidiFile(str(path))
    if midi.type == 2:
        raise ValueError("MIDI type 2(독립 패턴)는 지원하지 않습니다. type 0/1 MIDI가 필요합니다.")
    if midi.ticks_per_beat <= 0:
        raise ValueError("SMPTE 타임코드 기반 MIDI는 지원하지 않습니다.")
    tempo = []
    signatures = []
    warnings = []
    all_tracks = []
    end_tick = 0
    ignored_types: set[str] = set()
    for ti, track in enumerate(midi.tracks):
        tick = 0
        active: dict[tuple[int, int], deque[tuple[int, int]]] = defaultdict(deque)
        notes = []
        for msg in track:
            tick += msg.time
            if msg.type == "set_tempo":
                tempo.append((tick, msg.tempo, ti))
            elif msg.type == "time_signature":
                signatures.append((tick, msg.numerator, msg.denominator, ti))
            elif msg.type == "note_on" and msg.velocity > 0:
                active[(msg.channel, msg.note)].append((tick, msg.velocity))
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                stack = active[(msg.channel, msg.note)]
                if not stack:
                    warnings.append(f"트랙 {ti + 1}: 대응되는 note_on이 없는 note_off (tick {tick})")
                    continue
                begin, velocity = stack.popleft()
                if tick > begin:
                    notes.append(Note(begin, tick, msg.note, msg.channel, velocity))
                else:
                    warnings.append(f"트랙 {ti + 1}: 길이 0 음표 제외 (tick {tick})")
            elif msg.type == "control_change" and msg.control == 64:
                ignored_types.add("sustain pedal CC64")
            elif msg.type in {"pitchwheel", "aftertouch", "polytouch", "program_change"}:
                ignored_types.add(msg.type)
        for (channel, pitch), stack in active.items():
            if stack:
                raise ValueError(f"트랙 {ti + 1}: note_off 없는 음표 {pitch} ({len(stack)}건)")
        end_tick = max(end_tick, tick)
        all_tracks.append(notes)
    if ignored_types:
        warnings.append("DSL에서 별도 표현 불가: " + ", ".join(sorted(ignored_types)))
    if any(n.channel == 9 for tr in all_tracks for n in tr):
        warnings.append("드럼 채널 10은 음높이로 변환됩니다. 타악기 음색은 재현되지 않습니다.")
    if any(n.velocity != 100 for tr in all_tracks for n in tr):
        warnings.append("MIDI velocity(강약)는 DSL에 반영되지 않습니다.")
    # Tempo and time signature messages at the same tick: last one wins.
    tempo = sorted(tempo, key=lambda x: (x[0], x[2]))
    signatures = sorted(signatures, key=lambda x: (x[0], x[3]))
    sig_dict = {0: (4, 4)}
    for tick, n, d, _ in signatures:
        sig_dict[tick] = (n, d)
    return MidiData(
        midi, all_tracks,
        TimeMap(midi.ticks_per_beat, [(t, v) for t, v, _ in tempo]),
        [(tick, n, d) for tick, (n, d) in sorted(sig_dict.items())],
        warnings, end_tick,
    )


def quantize(beat: Fraction, grid: Fraction) -> Fraction:
    scaled = beat / grid
    # Integer nearest grid position, with .5 rounding up.
    return (scaled.numerator * 2 + scaled.denominator) // (2 * scaled.denominator) * grid


def prepare_events(notes: list[Note], tempo_map: TimeMap, mode: str, grid_den: int) -> list[Event]:
    groups: dict[tuple[Fraction, Fraction], list[int]] = defaultdict(list)
    step = Fraction(4, grid_den)
    for n in notes:
        s, e = tempo_map.beat(n.start), tempo_map.beat(n.end)
        if mode == "readable":
            s, e = quantize(s, step), quantize(e, step)
            e = max(e, s + step)
        if e <= s:
            raise ValueError("양수가 아닌 음표 길이가 확인되었습니다.")
        groups[(s, e)].append(n.pitch)
    return sorted(
        (Event(s, e, tuple(sorted(pitches))) for (s, e), pitches in groups.items()),
        key=lambda x: (x.start, x.end, x.pitches),
    )


def allocate_voices(events: list[Event]) -> list[list[Event]]:
    """Interval partition into non-overlapping sequences, never emit nonzero pull.

    This avoids the DSL's unspecified reset semantics for its inherited pull
    field, and remains correct for partially overlapping notes of all lengths.
    """
    voices: list[list[Event]] = []
    available: list[tuple[Fraction, int]] = []
    for event in events:
        if available and available[0][0] <= event.start:
            _, voice = heappop(available)
        else:
            voice = len(voices)
            voices.append([])
        voices[voice].append(event)
        heappush(available, (event.end, voice))
    return voices


def pitch_name(number: int, middle_c: int) -> str:
    return f"{NAMES[number % 12]}{number // 12 - 5 + middle_c}"


def numeric(value: Fraction, decimals: int = 12) -> str:
    """Serialize fraction to a legal non-exponent decimal DSL number."""
    if value <= 0:
        raise ValueError(f"분모 표현은 0보다 커야 합니다: {value}")
    if value.denominator == 1:
        return str(value.numerator)
    s = f"{float(value):.{decimals}f}".rstrip("0").rstrip(".")
    if not s or float(s) <= 0:
        raise ValueError("너무 짧은 길이로 0이 출력되었습니다. decimals를 늘리세요.")
    return s


def denominator(beats: Fraction, decimals: int) -> str:
    return numeric(Fraction(4) / beats, decimals)


def measure_starts(data: MidiData, last_note_tick: int) -> list[tuple[Fraction, int, int]]:
    """Time-signature aware bar boundaries (time signatures on unusual ticks start new bars)."""
    result = []
    changes = data.signatures
    ppq = data.midi.ticks_per_beat
    for idx, (start, num, den) in enumerate(changes):
        next_tick = changes[idx + 1][0] if idx + 1 < len(changes) else last_note_tick + 1
        bar_length = Fraction(ppq * 4 * num, den)
        if bar_length <= 0:
            raise ValueError("잘못된 MIDI 박자표")
        t = Fraction(start)
        while t < next_tick and t <= last_note_tick:
            result.append((data.time_map.beat(t), num, den))
            t += bar_length
    return result


def make_dsl(data: MidiData, *, mode="precise", measures=True, grid_den=16,
             middle_c=4, decimals=12, include_timbre=True,
             input_name="input.mid") -> tuple[str, dict]:
    if grid_den <= 0:
        raise ValueError("grid_den은 양수여야 합니다.")
    nonempty_tracks = [(i + 1, notes) for i, notes in enumerate(data.tracks) if notes]
    note_count = sum(len(notes) for _, notes in nonempty_tracks)
    max_end_tick = max((n.end for _, notes in nonempty_tracks for n in notes), default=0)
    bars = measure_starts(data, max_end_tick) if measures and note_count else []
    bar_points = [b[0] for b in bars]

    results: list[str] = [
        "$ MIDI → Sequence DSL 변환", "$ Source: " + input_name.replace("\n", " "),
        "$ Mode: " + mode + (f" (1/{grid_den} grid)" if mode == "readable" else ""),
        "$ Time: 4 = quarter note = 1 beat, 8 = eighth = 0.5 beat; Delay에도 적용",
        "$ Overlap: 연주 구간 겹침은 추가 Seq로 분리하여 보존 (당김 필드 0 사용)",
        "$ Velocity/악기/페달/피치벤드/타악기 음색은 DSL에서 보존되지 않을 수 있음",
        "$ Tempo changes: 실제 MIDI 시간을 고정 BPM 타임라인에 펼쳐서 재현",
        "$ Timbre/ADSR below are illustrative approximations, NOT MIDI instrument samples",
        "",
    ]
    summary = {"input": input_name, "mode": mode, "bpm": round(data.time_map.bpm, 6),
               "midi_tracks": len(data.tracks), "note_count": note_count,
               "sequence_count": 0, "play_events": 0, "measure_count": len(bars),
               "tempo_changes": max(0, len(data.time_map.ticks) - 1),
               "warnings": list(data.warnings)}
    for track_num, raw_notes in nonempty_tracks:
        events = prepare_events(raw_notes, data.time_map, mode, grid_den)
        voices = allocate_voices(events)
        for voice_num, voice in enumerate(voices, 1):
            summary["sequence_count"] += 1
            seq_num = summary["sequence_count"]
            results += [f"- Seq {seq_num}",
                        f"$ MIDI 트랙 {track_num}: {data.midi.tracks[track_num - 1].name or '(이름 없음)'} / Voice {voice_num}"]
            if include_timbre:
                results += [TIMBRE, ADSR]
            results += [f"*bpm{numeric(Fraction(60000000, data.time_map.base_tempo), 6)}", ""]
            cursor = Fraction(0)
            last_bar = -1

            def announce(position: Fraction):
                nonlocal last_bar
                upto = bisect_right(bar_points, position) - 1
                while last_bar < upto:
                    last_bar += 1
                    _, n, d = bars[last_bar]
                    if results[-1] != "":
                        results.append("")
                    results.append(f"$ {last_bar + 1:03d}마디 ({n}/{d})")

            if measures:
                announce(cursor)
            for event in voice:
                if event.start < cursor:
                    raise ValueError("내부 오류: 시퀀스 이벤트가 겹쳤습니다.")
                while cursor < event.start:
                    if measures:
                        announce(cursor)
                        next_idx = bisect_right(bar_points, cursor)
                        next_bar = bar_points[next_idx] if next_idx < len(bars) else event.start
                        rest_end = min(event.start, next_bar)
                    else:
                        rest_end = event.start
                    if rest_end <= cursor:
                        raise ValueError("내부 오류: Delay 분할 실패")
                    results.append(denominator(rest_end - cursor, decimals))
                    cursor = rest_end
                if measures:
                    announce(event.start)
                p = " ".join(pitch_name(i, middle_c) for i in event.pitches)
                results.append(f"{p} {denominator(event.end - event.start, decimals)} 0")
                cursor = event.end
                summary["play_events"] += 1
            results += ["", f"$ Seq {seq_num} 끝: {float(cursor):.6f}박", ""]

    if note_count == 0:
        summary["warnings"].append("음표가 없어 빈 DSL을 생성했습니다.")
    return "\n".join(results).rstrip() + "\n", summary



def verify_output(dsl: str, data: MidiData, *, mode: str, grid_den: int, middle_c: int) -> float:
    """Re-parse emitted DSL and compare every note onset/offset to MIDI.

    Assumes that a Seq starts with pull=0, that `0` inherits that pull, and
    that standalone denominators are delays. Returns worst error in beats.
    """
    pitch_re = re.compile(r"^([a-g])(#?)(-?\d+)$")
    seen: list[tuple[int, float, float]] = []
    clock = 0.0
    has_seq = False
    for raw in dsl.splitlines():
        line = raw.split("$", 1)[0].strip()
        if not line:
            continue
        if line.startswith("- Seq "):
            has_seq = True
            clock = 0.0
            continue
        if line.startswith(("~", "+", "!", "*")):
            continue
        if not has_seq:
            raise ValueError(f"시퀀스 밖에서 명령 발견: {line}")
        tokens = line.split()
        if len(tokens) == 1:
            clock += 4.0 / float(tokens[0])
            continue
        if len(tokens) < 3 or tokens[-1] != "0":
            raise ValueError(f"검증 실패: 지원하지 않는 노트 문법: {line}")
        duration = 4.0 / float(tokens[-2])
        for word in tokens[:-2]:
            match = pitch_re.fullmatch(word)
            if not match:
                raise ValueError(f"검증 실패: 음계 문법: {word}")
            midi_pitch = ((int(match.group(3)) + 5 - middle_c) * 12
                          + NAMES.index(match.group(1) + match.group(2)))
            seen.append((midi_pitch, clock, clock + duration))
        clock += duration

    expected: list[tuple[int, float, float]] = []
    step = Fraction(4, grid_den)
    for notes in data.tracks:
        for note in notes:
            s, e = data.time_map.beat(note.start), data.time_map.beat(note.end)
            if mode == "readable":
                s = quantize(s, step)
                e = max(quantize(e, step), s + step)
            expected.append((note.pitch, float(s), float(e)))
    expected.sort()
    seen.sort()
    if len(expected) != len(seen):
        raise ValueError(f"변환 검증 실패: 음표 {len(expected)}개 → {len(seen)}개")
    max_error = 0.0
    for (p, s, e), (pp, ss, ee) in zip(expected, seen):
        if p != pp:
            raise ValueError(f"변환 검증 실패: 음높이 {p} != {pp}")
        max_error = max(max_error, abs(s - ss), abs(e - ee))
    if max_error > 1e-7:
        raise ValueError(f"변환 검증 실패: 시간차 {max_error:.8g}박")
    return max_error


def run(input_path: Path, output: Path, *, mode="precise", measures=True,
        grid_den=16, middle_c=4, decimals=12, include_timbre=True):
    data = extract_midi(input_path)
    dsl, summary = make_dsl(data, mode=mode, measures=measures, grid_den=grid_den,
                            middle_c=middle_c, decimals=decimals,
                            include_timbre=include_timbre, input_name=input_path.name)
    summary["max_timing_error_beats"] = verify_output(
        dsl, data, mode=mode, grid_den=grid_den, middle_c=middle_c
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dsl, encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="MIDI → Sequence DSL 변환")
    parser.add_argument("input", type=Path, help="입력 .mid / .midi")
    parser.add_argument("-o", "--output", type=Path, help="저장할 .seq 경로 (기본: MIDI 옆)")
    parser.add_argument("--mode", choices=("precise", "readable"), default="precise")
    parser.add_argument("--grid", type=int, default=16, help="readable 격자: 기본 16분음표")
    parser.add_argument("--no-measures", action="store_true", help="마디 주석을 생략")
    parser.add_argument("--middle-c", type=int, default=4, help="MIDI 60의 옥타브 (기본 C4)")
    parser.add_argument("--decimals", type=int, default=12, help="분모 값 소수점 자리수")
    parser.add_argument("--no-timbre", action="store_true", help="음색/ADSR 추정 코드를 생략")
    parser.add_argument("--json", action="store_true", help="요약을 JSON으로 출력")
    args = parser.parse_args(argv)
    if not args.input.is_file():
        parser.error(f"MIDI 파일을 찾을 수 없습니다: {args.input}")
    if args.decimals not in range(6, 16):
        parser.error("--decimals는 6~15여야 합니다")
    if not args.input.suffix.lower() in (".mid", ".midi"):
        parser.error(".mid 또는 .midi 파일이 필요합니다")
    out = args.output or args.input.with_name(args.input.stem + f"_{args.mode}.seq")
    try:
        report = run(args.input, out, mode=args.mode, measures=not args.no_measures,
                     grid_den=args.grid, middle_c=args.middle_c,
                     decimals=args.decimals, include_timbre=not args.no_timbre)
    except (ValueError, OSError, EOFError) as exc:
        parser.exit(2, f"변환 실패: {exc}\n")
    report["output"] = str(out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"저장 완료 (검증 통과): {out}\nMIDI 음표 {report['note_count']}개 → "
              f"연주 이벤트 {report['play_events']}개 / Seq {report['sequence_count']}개 / "
              f"마디 {report['measure_count']}개 / BPM {report['bpm']}")
        for warning in report["warnings"]:
            print("주의: " + warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
