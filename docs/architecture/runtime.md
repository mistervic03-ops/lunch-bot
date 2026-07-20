# 런타임 아키텍처

## 결정

밥라투스트라는 사내 서버에서 서로 책임이 다른 두 Python 프로세스로 실행한다. 정기 추천은 기존처럼 단발성 작업으로 유지하고, Slack 링크 버튼의 요청을 ACK하기 위한 작은 Socket Mode 서비스만 상시 실행한다.

```text
systemd timer
    ↓
Python 단발성 작업
    ├── Google Sheet 후보와 추천 로그 읽기
    ├── 최근 Slack 번호 반응 집계와 로그 갱신
    ├── 공정 순환 추천 계산
    ├── Slack 점심 채널 게시
    ├── Google Sheet 추천 로그 추가
    └── 실패 시 Slack 운영 채널 알림

systemd가 일일 작업 실패 감지
    ↓
별도 Python oneshot 실패 알림
    └── Slack 운영 채널에 journal 확인 안내

bapratustra-slack.service
    └── Socket Mode 연결 유지와 interactive 요청 ACK
```

## 기술 스택

| 영역 | 선택 |
|---|---|
| 언어 | Python 3.11 이상 |
| 의존성 격리 | Python `venv` |
| 의존성 명세 | 버전을 고정한 `requirements.txt` |
| 실행 | 정기 추천은 systemd oneshot, Slack 상호작용은 systemd 상시 service |
| 일정 | systemd timer |
| Slack | 공식 `slack_sdk`로 Web API 호출과 Socket Mode 연결 |
| Google Sheets | Google 공식 Python API Client와 `google-auth` |
| Google 인증 | 전용 Service Account에 대상 Spreadsheet만 직접 공유 |
| 설정 | 환경변수와 `.env`, 단일 불변 `Settings` 구조에서 검증 |
| 시간대 | `Asia/Seoul` 명시 |
| 테스트 | `pytest`; 순수 로직 단위 테스트와 외부 클라이언트 대역 테스트 |
| 운영 로그 | systemd journal과 비공개 `#밥괘-운영` 채널 |

서버에 실제로 설치된 Python 버전을 확인한 뒤 지원 범위 안에서 하나의 버전으로 고정한다.

운영 의존성은 `requirements.txt`, 테스트 의존성은 이를 포함하는 `requirements-dev.txt`에 각각 고정한다.

Google Cloud 프로젝트에는 Sheets API와 초기 파일 생성·공유에 사용한 Drive API가 활성화되어 있다. 일일 애플리케이션은 Drive API를 호출하지 않는다. 드라이런은 Sheets 읽기 전용 인증 범위를 사용하고, 실제 일일 작업은 좋아요 갱신과 추천 로그 추가를 위해 Sheets 쓰기 범위를 사용한다.

## 선택 이유

- 정기 추천은 수신 이벤트와 무관하므로 단발성 작업으로 남긴다.
- URL 버튼도 Slack의 interaction payload를 만들기 때문에 작은 상시 서비스가 이를 빠르게 ACK한다.
- 스케줄을 운영체제에 맡기면 애플리케이션 재시작과 내부 스케줄러 상태를 관리할 필요가 없다.
- 기존 사내 Slack 봇이 Python, `venv`, systemd와 journal로 운영되고 있어 운영 지식을 재사용할 수 있다.
- Google Sheet와 Slack 호출은 모두 공식 Python 클라이언트가 지원한다.
- 상호작용 서비스는 ACK만 담당하므로 웹 서버, 별도 데이터베이스와 범용 Slack 프레임워크가 필요하지 않다.

## 의도적으로 제외하는 구성

MVP에서는 다음을 사용하지 않는다.

- FastAPI 또는 Flask
- Slack Bolt
- Slash Command와 Slack 이벤트 구독
- APScheduler 같은 프로세스 내부 스케줄러
- PostgreSQL, Redis 또는 별도 데이터베이스
- Docker와 컨테이너 이미지
- 비동기 코드
- GPU와 CUDA
- ORM과 범용 저장소 추상화

이 항목은 금지 목록이 아니라 현재 요구에 필요하지 않은 구성이다. 실제 요구가 생기면 트레이드오프를 다시 검토한다.

## 코드 경계

과도한 계층을 만들지 않고 다음 책임만 분리한다.

```text
실행 진입점
├── 설정 로드와 검증
├── Google Sheet 읽기와 로그 추가
├── 순수 추천 계산
├── Slack 메시지 생성과 전송
├── Socket Mode interactive 요청 ACK
└── 실행 흐름과 오류 분류
```

- 추천 계산은 Slack이나 Google 클라이언트를 직접 호출하지 않는다.
- Google Sheet 접근과 Slack 전송은 서로를 알지 않는다.
- 환경변수는 설정 모듈 한 곳에서만 읽는다.
- 단일 사용처를 위한 인터페이스나 플러그인 시스템은 만들지 않는다.
- 외부 클라이언트는 테스트에서 가짜 구현으로 바꿀 수 있게 함수나 객체에 전달한다.
- Slack 게시 함수는 링크 미리보기를 끄고 응답의 채널 ID와 메시지 ID를 검증한다.
- 연결 테스트는 실제 Slack 게시와 반응 권한을 검증하지만 추천 로그 쓰기와 분리한다.

현재 파일별 책임과 구현 여부는 `docs/operations/development.md`에서 확인한다.

## 인증과 비밀정보

- Slack Bot Token, App-Level Token과 Google Service Account 인증 정보는 저장소에 커밋하지 않는다.
- Slack 앱에는 초기 기능에 필요한 최소 권한만 부여한다.
- Slack Bot Token 권한은 `chat:write`, `pins:write`, `reactions:read`, `reactions:write`로 제한한다. `pins:write`는 온보딩 메시지 자동 고정에만 사용한다.
- Slack 앱 설정은 `slack/app-manifest.json`으로 버전 관리하며 토큰과 채널 ID는 포함하지 않는다.
- 봇을 점심 채널과 `#밥괘-운영` 채널에 직접 초대한다.
- Google Service Account에는 도메인 전체 위임이나 Workspace 관리자 권한을 부여하지 않는다.
- 대상 Spreadsheet만 Service Account 이메일에 편집 권한으로 공유한다.
- 실제 비밀정보는 systemd가 읽는 서버의 환경 파일 또는 제한된 인증 파일에 보관한다.

## Slack 상호작용 서비스와 향후 확장

`bapratustra-slack.service`는 현재 링크 버튼 요청을 ACK하는 책임만 가진다. 정기 추천 계산이나 Sheet 쓰기는 수행하지 않는다. 기존 `slack_sdk`의 Socket Mode Client를 사용하며, 한 가지 ACK를 위해 Slack Bolt를 추가하지 않는다.

초기에는 Slash Command를 제공하지 않는다. 다음 요구가 실제로 확인되면 현재 서비스에 작은 핸들러를 추가하거나, 라우팅과 상태 관리가 복잡해질 때 Slack Bolt 도입을 다시 검토한다.

- 개인 또는 조건부 추천
- Slack 모달을 통한 식당과 메뉴 등록
- 비개발자 운영자를 위한 미리보기, 수동 게시 또는 상태 확인

확장할 때도 정기 게시를 반드시 상시 서비스로 옮길 필요는 없다.

```text
bapratustra.timer
    └── 정기 게시 작업

bapratustra-slack.service
    ├── 현재 URL 버튼 ACK
    └── 향후 필요시 Slash Command와 모달
```

두 실행 경로가 같은 추천 계산과 Google Sheet 코드를 호출하도록 구성한다. 미래 확장을 위해 현재 범용 프레임워크를 미리 만들지는 않는다.

## 컨테이너 도입을 다시 검토할 조건

- DGX Spark의 Python 환경과 의존성 충돌이 실제로 발생함
- 배포 재현에 반복적인 문제가 생김
- 다른 서버로 이전해야 함
- 사내 배포 표준이 컨테이너 중심으로 바뀜

이 조건이 생기기 전에는 기존 사내 운영 방식과 동일하게 `venv`와 systemd를 사용한다.

## systemd 일정 세부 정책

- timer의 `OnCalendar`에 `Asia/Seoul`을 직접 명시한다.
- 서버 중단 중 놓친 추천을 뒤늦게 올리면 오전 11시 게시라는 제품 약속을 어기므로 catch-up 실행을 사용하지 않는다.
- oneshot service는 `python -m bapratustra --run-daily`를 실행한다.
- oneshot service가 120초를 넘기면 실패로 종료한다.
- service의 `OnFailure`는 별도 oneshot 알림 unit을 실행한다. 이 알림은 Google 설정과 무관하게 Slack Bot Token과 운영 채널 ID만 사용한다.
- 안전한 읽기와 좋아요 동기화만 애플리케이션에서 최대 세 번 시도하며 Slack 추천 게시와 후속 기록은 재시도하지 않는다.
- 상시 service는 `python -m bapratustra --run-slack-service`를 실행하고 비정상 종료 때만 5초 후 재시작한다.
- 실제 점심 채널과 운영 채널에서 한 차례 전체 흐름을 검증하고 서버 경로와 권한을 확정한 뒤 timer를 활성화한다.
