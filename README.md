# 밥라투스트라

매일 평일 오전 11시(KST), 사내 Slack 채널에 세 곳의 점심 후보를 알려주는 봇이다. 과장되게 진지한 철학자가 점심의 세 갈래 길을 선언하는 캐릭터를 사용하며, 후보는 직원들이 공동 편집하는 Google Sheet에서 가져온다.

현재 저장소에는 공정 순환 추천, Sheet와 전당 링크 버튼이 있는 Slack 게시, 번호 반응, Google Sheets 추천 로그와 좋아요 동기화, 채널 온보딩, 최소 Socket Mode ACK 서비스와 사내 리더보드 웹페이지가 구현되어 있다. Google Sheet를 대체할 가치가 있는지 확인하기 위한 별도 SQLite 후보 관리 알파도 있지만, 현재 봇과 전당은 계속 Sheet만 사용한다.

## 개발 환경

Python 3.11 이상을 사용한다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

`.env`에 실제 값을 넣고 Google Service Account JSON 파일을 지정한 뒤 설정을 확인한다.

```bash
python -m bapratustra
```

이 명령은 외부 API를 호출하지 않고 전체 설정만 검증한다. Slack 설정 전에도 실제 Google Sheet의 읽기와 추천 미리보기를 확인할 수 있다.

```bash
python -m bapratustra --dry-run
```

드라이런은 후보와 추천 로그를 모두 읽어 공정 순환 추천을 계산하지만 Sheet를 수정하거나 Slack 메시지를 보내지 않는다. 유효 후보가 없으면 연결 성공을 출력한 뒤 종료 코드 `1`을 반환한다.

Slack 앱을 설치하고 테스트 채널을 연결한 뒤에는 명확히 표시된 연결 테스트 메시지를 한 건 게시할 수 있다.

```bash
python -m bapratustra --test-slack
```

이 명령은 실제 Sheet의 후보와 이력을 사용하고 번호 반응을 추가·조회하지만 `recommendation_log`에는 기록하지 않는다. 반복 실행하면 테스트 메시지가 추가로 남으므로 명시적인 연결 검증에만 사용한다.

실제 일일 작업은 다음 명령으로 한 번 실행한다.

```bash
python -m bapratustra --run-daily
```

이 명령은 최근 다섯 추천 메시지의 좋아요를 Sheet에 갱신하고, 당일 중복 게시를 확인한 뒤 실제 점심 채널 게시, 추천 로그 기록과 번호 반응 추가를 수행한다. Slack과 Sheet를 실제로 변경하므로 테스트 용도로 반복 실행하지 않는다.

채널 안내는 한 번 게시하고 같은 명령에서 자동으로 고정한다.

```bash
python -m bapratustra --post-onboarding
```

링크 버튼 요청을 ACK하는 상시 서비스는 App-Level Token이 설정된 환경에서 실행한다.

```bash
python -m bapratustra --run-slack-service
```

사내 리더보드를 로컬에서 확인한다.

```bash
python -m uvicorn bapratustra.web:create_app --factory --host 127.0.0.1 --port 8030
```

페이지는 실제 Sheet를 읽어 `http://127.0.0.1:8030/`에 표시하고 5분간 캐시한다. 운영 접근 범위와 지표 정의는 `docs/features/leaderboard.md`를 따른다.

후보 관리 알파는 기존 운영과 분리된 DB와 포트에서 실행한다. 최초 실행 전에 `.env`의 알파 경로를 정하고 현재 Sheet를 읽기 전용으로 한 번 가져온다.

```bash
python -m bapratustra --import-sheet-to-alpha
python -m uvicorn bapratustra.alpha_web:create_app --factory --host 127.0.0.1 --port 8031
```

운영에서는 별도 systemd 서비스가 알파 웹을 자동 재시작하고, 매일 03:30 KST에 검증된 백업을 만든 뒤 최근 30개만 보존한다. 화면과 백업, 평가 및 Sheet 복귀 기준은 `docs/features/candidate-management-alpha.md`를 따른다.

## 테스트

```bash
pytest
```

## 문서

작업 전에는 반드시 `AGENTS.md`를 먼저 읽는다. 제품 범위, 데이터 스키마, 기능 및 운영 결정은 `docs/README.md`에서 찾을 수 있다.
