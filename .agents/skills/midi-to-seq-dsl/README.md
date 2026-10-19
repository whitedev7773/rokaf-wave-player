# MIDI → Sequence DSL Skill

`.mid` / `.midi` 악보를 독자적인 텍스트 음악 DSL `.seq`로 변환하는 **Agent Skills 규격**의 스킬입니다.

## 구성

- `SKILL.md`: 에이전트가 읽는 작업 지침
- `scripts/convert.py`: MIDI 변환기 (Python + `mido`)
- `references/syntax.md`: DSL 문법과 보존 범위
- `tests/test_convert.py`: 자동 검증

## 로컬에서 실행

```bash
python -m pip install -r requirements.txt
python scripts/convert.py "example.mid" --mode precise -o "example.seq"
python scripts/convert.py "example.mid" --mode readable --grid 16 -o "example_readable.seq"
python -m unittest discover -s tests -v
```

옵션 `--no-measures`: 마디 주석 제거, `--middle-c 3`: MIDI 60을 `c3`으로 표시, `--no-timbre`: 임의 합성음 설정 제외.

## 설치

- 에이전트가 Agent Skills 표준을 지원한다면 이 디렉터리를 해당 환경의 Skills 검색 경로에 놓습니다.
- Codex 프로젝트에서는 `.agents/skills/midi-to-seq-dsl/` 폴더로 복사할 수 있습니다.
- 이 ZIP에는 **스킬 파일 자체**가 담겨 있습니다. ChatGPT나 Codex에 자동 설치된 것은 아닙니다.

## 정확도

MIDI 음표의 onset/offset, 음높이, 동시에 시작·끝나는 화음, BPM 변화, 박자표에 따른 마디 주석을 다룹니다. 정확한 이벤트 보존을 위해 필요 시 MIDI 한 트랙을 여러 `Seq`로 나눕니다. MIDI 악기·음량·페달·드럼 음색을 동일하게 재현하지는 않습니다.
