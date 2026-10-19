# ROKAF Wave Player

단일 HTML 파일로 동작하는 텍스트 기반 음악 시퀀서 플레이어입니다. 시퀀스별 BPM, 동시 재생 화음, Sweep, Delay 및 당김 값 등을 지원하며, 전체 오디오를 사전 렌더링한 뒤 재생합니다.

## 실행

`index.html`을 Chrome 또는 Edge에서 열면 됩니다. 서버 또는 별도의 빌드 과정이 필요하지 않습니다. `.seq` 코드 파일을 불러오거나 편집기에 직접 입력할 수 있습니다.

## 주요 기능

- 사용자 정의 Sequence DSL 편집 및 문법 검사
- 단음, 무제한 다중음 화음, Sweep, Delay 및 코드 내 `$` 주석
- 시퀀스별 독립 BPM, ADSR 및 사인파 배음 합성
- Web Workers 기반 고속 병렬 파형 렌더링 / Web Audio 렌더링 엔진 선택
- 전체 오디오를 렌더링 후 캐시에 보관하여 재생·일시정지·탐색·반복
- 소수점 분모 표기와 마디 관련 시퀀스 코드 지원

## 음표 길이

길이 숫자는 음표의 분모입니다. 예를 들어 `4` = 4분음표 = 1박, `8` = 8분음표 = 0.5박, `2` = 2분음표 = 2박입니다. 독립된 숫자 행은 동일한 기준의 쉼표(Delay)를 뜻합니다.

```text
$ Basic example
- Seq 1
*bpm120
c4 e4 g4 4 0
4
c5:c4 8 0
```

## MIDI → Sequence DSL 변환 스킬

이 저장소에는 MIDI(`.mid`/`.midi`)를 플레이어의 `.seq` 코드로 변환하는 **프로젝트 로컬 Agent Skill**도 포함되어 있습니다.

- 스킬 정의: [`.agents/skills/midi-to-seq-dsl/SKILL.md`](.agents/skills/midi-to-seq-dsl/SKILL.md)
- 변환 도구: [`.agents/skills/midi-to-seq-dsl/scripts/convert.py`](.agents/skills/midi-to-seq-dsl/scripts/convert.py)
- 상세 문법: [`.agents/skills/midi-to-seq-dsl/references/syntax.md`](.agents/skills/midi-to-seq-dsl/references/syntax.md)

Codex 등 프로젝트 스킬 탐색을 지원하는 에이전트는 `.agents/skills/` 아래의 스킬을 사용할 수 있습니다. 직접 실행하려면 Python 3와 `mido` 패키지가 필요합니다.

```bash
python -m pip install -r .agents/skills/midi-to-seq-dsl/requirements.txt

# MIDI의 실제 발음/종료 타이밍을 최대한 유지
python .agents/skills/midi-to-seq-dsl/scripts/convert.py "input.mid" --mode precise -o "output_precise.seq"

# 편집하기 쉬운 16분음표 격자 버전
python .agents/skills/midi-to-seq-dsl/scripts/convert.py "input.mid" --mode readable --grid 16 -o "output_readable.seq"

# 변환기 자동 테스트
python -m unittest discover -s .agents/skills/midi-to-seq-dsl/tests -v
```

**변환 원칙:** `4`는 4분음표(1박)이며, 길이가 같은 동시 발음 음표는 화음으로 묶습니다. 지속 시간이 다른 음표가 겹치면 별도 `Seq`로 분리해 타이밍을 보존합니다. 마디는 `$ 001마디 (4/4)` 같은 주석으로 구분합니다. 정밀 출력에도 소수점 반올림 오차는 남을 수 있습니다.

**주의:** MIDI의 악기 샘플, 음표별 Velocity, CC/페달 및 피치 벤드까지 동일하게 표현하는 것은 현재 DSL로 불가능합니다. 이 저장소에는 타인의 MIDI 원본 또는 변환 악보를 포함하지 않았습니다.

## GitHub Pages 배포

정적 사이트이므로 GitHub Pages로 배포할 수 있습니다. `.github/workflows/pages.yml` 워크플로가 포함되어 있습니다.

1. 저장소 **Settings → Pages**에서 배포 소스(Source)를 **GitHub Actions**로 설정합니다.
2. `main` 브랜치에 push하면 Pages 워크플로가 실행됩니다.
3. 배포가 완료되면 GitHub Pages가 제공하는 주소에서 플레이어를 열 수 있습니다.

예상 주소 형태: `https://whitedev7773.github.io/rokaf-wave-player/` (배포 후에만 유효).

## 참고

현재 플레이어는 MIDI 음색을 그대로 복원하는 샘플 플레이어가 아니라 사용자 정의 음색을 합성하는 신디사이저입니다. 동일한 입력도 렌더링 엔진에 따라 미세한 음색 차이가 있을 수 있습니다.

원본 코드: `index.html` (CSS/JavaScript 포함, 외부 런타임 의존성 없음)
