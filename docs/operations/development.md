# 개발과 검증

## 현재 구현 상태

현재 저장소는 초기 실행 골격 단계다.

- 구현됨: 환경변수 검증, 순수 추천 계산, Slack 메시지 문자열 생성, Google Sheets 후보와 추천 로그 읽기·검증, 추천 로그 일괄 추가 함수, 날짜·채널 중복 판정, 읽기 전용 드라이런, systemd 템플릿
- 미구현: Slack 게시와 번호 반응 추가, 추천 로그 쓰기의 실제 게시 흐름 연결, 좋아요 동기화, 운영 채널 오류 알림
- `python -m babgwe`는 설정만 검증하며 외부 API를 호출하지 않는다.
- 실제 일일 작업이 완성되기 전에는 `deploy/babgwe.service`와 `deploy/babgwe.timer`를 활성화하지 않는다.

## 코드 구조

```text
babgwe/
├── __main__.py        # 전체 설정 검증과 Google Sheets 드라이런 진입점
├── config.py          # 환경변수 로드와 불변 Settings 검증
├── sheets.py          # Sheets 클라이언트, 후보·로그 조회와 검증 및 로그 일괄 추가
├── recommendation.py  # 외부 API와 무관한 공정 순환 추천 계산
├── messaging.py       # 단일 Slack 메시지 문자열 생성
└── job.py             # 로그 행 생성, 이력 변환과 날짜·채널 중복 판정

tests/                 # 설정, 추천 계산, 메시지 포맷 단위 테스트
deploy/                # 아직 활성화하면 안 되는 systemd 템플릿
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

## 검증 명령

```bash
pytest
python -m babgwe
python -m babgwe --dry-run
```

첫 명령은 단위 테스트를 실행한다. 두 번째 명령은 전체 필수 설정과 인증 파일 경로만 검사한다. 세 번째 명령은 실제 `lunch_options` 탭을 읽고 행 오류와 추천 메시지를 터미널에 출력하지만 Sheet를 수정하거나 Slack에 게시하지 않는다.

드라이런에서 유효 후보가 없으면 Google 연결과 헤더 검증이 성공했더라도 종료 코드 `1`을 반환한다. 2026-07-20 최초 연동에서는 실제 Sheet 연결에 성공했고 후보가 비어 있어 `0 active option(s)`를 확인했다.

같은 날 직원용 한글 헤더와 서식을 적용한 뒤 Service Account 드라이런을 다시 실행하여 변경된 헤더를 정상 인식하는 것도 확인했다.

실제 식당 데이터를 등록한 뒤 실행한 드라이런에서는 오류 없이 활성 후보 6행을 읽고 서로 다른 식당 세 곳을 선택하여 가격, 추천인과 지도 링크가 포함된 메시지를 생성했다. 이 검증은 Sheet 읽기부터 후보 선택과 메시지 생성까지의 읽기 전용 경로가 실제 데이터로 동작함을 확인한 것이며 Slack 전송이나 추천 로그 기록은 수행하지 않았다.

추천 로그 읽기를 연결한 뒤에는 같은 실제 데이터와 빈 로그 탭을 함께 읽어 활성 후보 6행, 유효한 추천 이력 0행을 확인했다. 이후 로그가 쌓이면 드라이런도 해당 이력을 공정 순환 계산에 사용한다.

## systemd 템플릿 주의 사항

- 기본 경로는 애플리케이션 `/opt/babgwe`, 환경 파일 `/etc/babgwe/babgwe.env`, 인증 파일 `/etc/babgwe/google-service-account.json`이다.
- 서비스 계정 이름은 `babgwe`로 가정한다. 서버 운영 방식에 맞춰 설치 시 확정한다.
- timer는 `Asia/Seoul`을 명시해 월요일부터 금요일 오전 11시에만 실행한다.
- 놓친 실행을 나중에 게시하지 않도록 `Persistent=true`를 사용하지 않는다.
- 실제 배포 절차와 권한은 Slack/Sheets 연동이 완성될 때 별도로 확정하고 문서화한다.
