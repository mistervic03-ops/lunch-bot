# 개발과 검증

## 현재 구현 상태

현재 저장소는 실제 일일 작업까지 연결된 단계다.

- 구현됨: 환경변수 검증, 순수 추천 계산, Slack 메시지와 Sheet·전당 링크 버튼 생성·게시, 채널 온보딩 게시 명령, 링크 버튼 Socket Mode ACK, 번호 반응 추가·조회, 최근 다섯 메시지 좋아요 동기화, Google Sheets 후보와 추천 로그 읽기·검증 및 일괄 쓰기, 후보 웹의 Sheet 검색·중복 확인·한 행 추가, 안전한 읽기·동기화의 제한된 재시도, 날짜·채널 중복 판정, 운영 채널 알림, 실제 일일 작업, 읽기 전용 드라이런, Slack 연결 테스트 명령, systemd 실패 알림 명령, 사내 리더보드 집계·캐시·HTML과 health check, Slack App Manifest, systemd 템플릿
- 미구현: 월간 통계 게시, 번호 반응 추가 실패의 자동 복구
- `python -m bapratustra`는 설정만 검증하며 외부 API를 호출하지 않는다.
- `python -m bapratustra --run-daily`는 실제 Slack과 Google Sheet를 변경한다.
- `python -m bapratustra --post-onboarding`은 안내 메시지를 한 번 게시하고 즉시 자동 고정한다.
- `python -m bapratustra --run-slack-service`는 App-Level Token과 Bot Token만 읽어 Socket Mode 연결을 유지한다.
- 실제 점심·운영 채널에서 전체 흐름을 한 번 검증하기 전에는 `deploy/bapratustra.timer`를 활성화하지 않는다.
- 배포 전 코드 식별자를 `babgwe`에서 `bapratustra`로 하드 전환했다. 옛 Python 패키지, systemd unit과 `BABGWE_TIMEZONE` fallback은 제공하지 않는다.

## 코드 구조

```text
bapratustra/
├── __main__.py        # 설정 검증, 운영 명령과 두 런타임 진입점
├── config.py          # 환경변수 로드와 불변 Settings 검증
├── sheets.py          # Sheets 클라이언트, 후보·로그 조회와 검증 및 로그·좋아요 쓰기
├── recommendation.py  # 외부 API와 무관한 공정 순환 추천 계산
├── messaging.py       # Slack 추천·온보딩 메시지, 번호 반응과 운영 알림
├── interactions.py    # Socket Mode 연결과 interactive 요청 ACK
├── leaderboard.py     # 순수 리더보드 집계와 5분 스냅샷 캐시
├── web.py             # FastAPI 페이지, 오류 화면과 health check
├── alpha_web.py       # Sheet 기반 후보 간편 등록·검색 웹 화면
├── templates/         # 서버 렌더링 HTML
├── static/            # 리더보드 CSS, Pretendard와 공용 도메인 초상·출처
└── job.py             # 좋아요 동기화와 전체 일일 실행 흐름

tests/                 # 설정, 추천 계산, 메시지 포맷과 웹 화면 단위 테스트
deploy/                # 전체 흐름 검증 후 활성화할 systemd 템플릿
slack/                 # 비밀정보가 없는 재현 가능한 Slack App Manifest
```

## Python과 의존성

- 지원 기준은 Python 3.11 이상이다.
- `requirements.txt`에는 운영 의존성만 정확한 버전으로 고정한다.
- `requirements-dev.txt`는 운영 의존성을 포함하고 `pytest`를 추가한다.
- 개발 환경은 저장소의 `.venv`를 사용한다.

현재 개발 머신의 기본 `/usr/bin/python3`는 3.9.6이므로 호환성 확인의 근거로 삼지 않는다. Python 3.11 이상인 가상환경에서 최종 검증해야 한다.

## 로컬 준비

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

실제 비밀정보는 `.env`와 저장소 밖의 Google Service Account JSON에 둔다. 두 파일은 커밋하지 않는다.
Slack 메시지의 `전당 둘러보기` 버튼은 `BAPRATUSTRA_LEADERBOARD_URL`을 사용한다. 사내망에서 구성원이 접근할 수 있는 전체 URL을 설정하며 코드나 문서에 실제 서버 주소를 고정하지 않는다.
`식당·메뉴 등록` 버튼은 `BAPRATUSTRA_CANDIDATE_URL`을 사용해 후보 간편 등록 화면으로 연결한다.

## 검증 명령

```bash
pytest
python -m bapratustra
python -m bapratustra --dry-run
python -m bapratustra --test-slack
python -m bapratustra --post-onboarding
python -m bapratustra --run-slack-service
python -m bapratustra --run-daily
python -m uvicorn bapratustra.web:create_app --factory --host 127.0.0.1 --port 8030
python -m uvicorn bapratustra.alpha_web:create_app --factory --host 127.0.0.1 --port 8031
```

첫 명령은 단위 테스트를 실행한다. 설정 검증과 드라이런은 외부 상태를 바꾸지 않는다. `--test-slack`은 버튼이 포함된 연결 테스트 메시지와 번호 반응을 게시·조회하되 추천 로그를 수정하지 않는다. `--post-onboarding`은 안내 메시지를 게시하고 자동 고정하므로 채널당 한 번만 실행한다. 게시 후 고정에 실패하면 이미 생성된 메시지의 채널과 ID를 출력하므로 원인을 해결하기 전에 명령을 반복하지 않는다. `--run-slack-service`는 종료할 때까지 Socket Mode 요청을 기다린다. `--run-daily`는 최근 좋아요를 갱신하고 실제 추천 게시·로그 기록·번호 반응 추가를 수행한다.

`--run-daily`는 외부 상태를 바꾸므로 단순 검증 목적으로 실행하지 않는다. 성공과 같은 날짜·채널의 중복 종료는 코드 `0`, 완료되지 않은 작업은 코드 `1`, 설정 또는 스키마 오류는 코드 `2`, 진입점까지 전달된 Slack API 오류는 코드 `3`을 반환한다.

리더보드 로컬 명령은 실제 Sheet를 읽고 `http://127.0.0.1:8030/`에 페이지를 제공한다. `http://127.0.0.1:8030/healthz`는 Sheet를 호출하지 않고 프로세스 상태만 확인한다. 운영에서는 `deploy/bapratustra-leaderboard.service`가 `0.0.0.0:8030`의 Uvicorn 단일 worker를 실행한다.

후보 간편 등록 웹은 기존 Google Spreadsheet ID와 Service Account 파일만 사용한다. 검색은 활성·비활성 후보를 모두 읽고, 등록은 중복이 없을 때 `lunch_options`에 활성 행 하나를 추가한다. 기존 행의 수정·삭제·비활성화는 웹에서 수행하지 않고 Sheet로 연결한다. 별도 DB, migration, 동기화와 백업 작업은 없다.

드라이런에서 유효 후보가 없으면 Google 연결과 헤더 검증이 성공했더라도 종료 코드 `1`을 반환한다. 2026-07-20 최초 연동에서는 실제 Sheet 연결에 성공했고 후보가 비어 있어 `0 active option(s)`를 확인했다.

같은 날 직원용 한글 헤더와 서식을 적용한 뒤 Service Account 드라이런을 다시 실행하여 변경된 헤더를 정상 인식하는 것도 확인했다.

실제 식당 데이터를 등록한 뒤 실행한 드라이런에서는 오류 없이 활성 후보 6행을 읽고 서로 다른 식당 세 곳을 선택하여 가격, 추천인과 지도 링크가 포함된 메시지를 생성했다. 이 검증은 Sheet 읽기부터 후보 선택과 메시지 생성까지의 읽기 전용 경로가 실제 데이터로 동작함을 확인한 것이며 Slack 전송이나 추천 로그 기록은 수행하지 않았다.

추천 로그 읽기를 연결한 뒤에는 같은 실제 데이터와 빈 로그 탭을 함께 읽어 활성 후보 6행, 유효한 추천 이력 0행을 확인했다. 이후 로그가 쌓이면 드라이런도 해당 이력을 공정 순환 계산에 사용한다.

Slack 연결 테스트에서는 실제 테스트 채널에 표시된 메시지 한 건을 게시하고 세 번호 반응을 추가한 뒤 API로 다시 읽는 데 성공했다. 이 테스트는 추천 로그를 수정하지 않았다.

2026-07-20에는 테스트 채널에서 `--run-daily` 전체 흐름을 실행했다. 일반 추천 메시지 한 건 게시, `recommendation_log` 세 행 추가, 세 번호 반응 추가가 모두 성공했다. 실행 후 드라이런에서 활성 후보 6행과 추천 이력 3행을 읽었고, Slack API 재조회에서 `1️⃣`, `2️⃣`, `3️⃣` 반응이 각각 한 개씩 확인됐다. 실제 직원용 채널 전환과 DGX Spark 배포는 아직 수행하지 않았다.

같은 날 개인 계정으로 세 번째 후보에 반응한 뒤 `--run-daily`를 다시 실행했다. 새 메시지 없이 같은 날짜·채널의 중복 실행으로 종료했고, Slack의 `3️⃣` 원본 반응 2개에서 봇 반응 1개를 제외한 좋아요 1개가 로그에 기록됐다. `1️⃣`, `2️⃣`의 좋아요는 0으로 유지됐다. 비공개 운영 채널에도 실제 오류가 아님을 표시한 테스트 알림을 보내 전송 권한을 확인했다.

제품명을 밥라투스트라로 변경한 뒤 실제 Sheet를 사용한 드라이런에서 `📜` 제목, 고정 선언 두 문장, 후보 목록과 평범한 반응 안내가 의도한 순서로 출력되는 것을 확인했다. 이 검증은 Slack 앱의 설치된 표시 이름이나 외부 Google 자원 이름을 변경하지 않았다.

내부 이름을 `bapratustra`로 하드 전환한 뒤 새 모듈 import와 설정 검증 명령, 실제 Sheet 드라이런이 성공했다. 옛 `babgwe` Python 모듈은 더 이상 import되지 않는다. Google Cloud 프로젝트, Service Account와 기존 로컬 인증 파일 경로는 외부 레거시 식별자로 유지한다.

같은 날 Google Cloud 프로젝트 표시 이름을 `Bapratustra Lunch Bot`, Spreadsheet 제목을 `밥라투스트라 점심 추천`으로 변경했다. 재조회에서 프로젝트 ID, Spreadsheet ID와 `lunch_options`, `recommendation_log` 탭 이름이 유지된 것을 확인했다. Service Account 이메일과 기존 로컬 인증 파일 경로는 변경하지 않았다.

재브랜딩 후 `python -m bapratustra --test-slack`을 실행해 테스트 채널에 표시된 연결 테스트 메시지 한 건을 게시했다. `1️⃣`, `2️⃣`, `3️⃣` 추가와 API 재조회가 성공했고 추천 로그가 변경되지 않은 것을 확인했다.

웹 전당이 Sheet 리더보드를 대체한 뒤 `인기 메뉴` 탭을 삭제하고 `lunch_options`, `recommendation_log` 두 원본 탭이 남은 것을 재확인했다. 서버 환경에는 메시지용 `BAPRATUSTRA_LEADERBOARD_URL`을 추가했으며, `점심 후보 보태기`와 `전당 둘러보기` 버튼이 포함된 새 온보딩 메시지를 게시하고 자동 고정했다. 앱은 `pins:read`를 요청하지 않으므로 이전 온보딩의 고정 해제는 Slack에서 직접 수행한다.

Slack 앱에는 니체에서 영감을 받은 가상의 밥라투스트라 캐릭터 아이콘을 적용했다. 원본 이미지 파일은 저장소에 포함하지 않은 상태이므로 서버 배포에는 추가 이미지 자산이 필요하지 않다.

## systemd 템플릿 주의 사항

- 기본 경로는 애플리케이션 `/opt/bapratustra`, 환경 파일 `/etc/bapratustra/bapratustra.env`, 인증 파일 `/etc/bapratustra/google-service-account.json`이다.
- 서버의 Unix 사용자와 그룹 이름은 `bapratustra`로 가정한다. 서버 운영 방식에 맞춰 설치 시 확정한다.
- timer는 `Asia/Seoul`을 명시해 월요일부터 금요일 오전 11시에만 실행한다.
- 놓친 실행을 나중에 게시하지 않도록 `Persistent=true`를 사용하지 않는다.
- service는 `python -m bapratustra --run-daily`를 실행한다.
- service는 120초 실행 제한과 `bapratustra-failure@.service`를 `OnFailure`로 사용한다.
- 실패 알림 service는 `python -m bapratustra --notify-systemd-failure <unit>`를 실행하며 Slack Bot Token과 운영 채널 ID만 필요하다.
- `bapratustra-slack.service`는 Socket Mode 연결을 상시 유지하며 App-Level Token과 Bot Token만 필요하다. 비정상 종료 때 재시작하지만 정상 종료는 자동 재시작하지 않는다.
- `bapratustra-leaderboard.service`는 Google Spreadsheet ID와 읽기 가능한 Service Account 파일만 필요하다. 공용 환경 파일에서 Slack 토큰, 채널 설정과 메시지용 전당 URL을 제거한 뒤 `.env` 자동 로드를 비활성화한다. 내부 네트워크의 `0.0.0.0:8030`에서 단일 worker로 실행하고 비정상 종료 때 재시작한다.
- `bapratustra-alpha.service`는 Google 설정만 전달받아 Uvicorn 단일 worker를 `0.0.0.0:8031`에서 실행하고 비정상 종료 때 재시작한다. Slack 토큰과 채널 설정은 이 프로세스에서 제거한다.
- 실제 배포 경로, 계정과 파일 권한은 DGX Spark 배포 시 확정하고 문서화한다.
