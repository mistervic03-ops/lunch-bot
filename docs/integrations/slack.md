# Slack 앱 설정과 인계

## 현재 구성

밥라투스트라는 워크스페이스 내부에서만 사용하는 일반 Slack 앱이다. 앱 설정의 재현 가능한 원본은 `slack/app-manifest.json`이다. Manifest에는 비밀정보나 워크스페이스별 채널 ID를 넣지 않는다.

초기 앱은 다음 기능만 사용한다.

- Slack 앱 이름: `밥라투스트라`
- 봇 사용자 표시 이름: `bapratustra`
- 정기 메시지 게시
- 정기 메시지와 온보딩의 Google Sheet 링크 버튼
- 후보별 번호 반응 추가
- 기존 번호 반응 수 조회
- Socket Mode로 버튼 interaction payload ACK

Socket Mode와 Interactivity는 링크 버튼을 위해 사용한다. 일반 이벤트 구독, Slash Command와 Incoming Webhook은 사용하지 않는다.

## 현재 실제 연결 상태

| 항목 | 값 |
|---|---|
| 워크스페이스 | `bigxdata-official` |
| Team ID | `T09HV6RM5NX` |
| `auth.test` 내부 username | `babgwe` |
| Bot User ID | `U0BJHC7HXU4` |
| Bot ID | `B0BJAC5BL13` |

- 저장소의 Manifest는 앱 이름 `밥라투스트라`와 봇 사용자 표시 이름 `bapratustra`로 갱신되어 있다. `bot_user.display_name`은 Slack이 허용하는 `a-z`, `0-9`, `-`, `_`, `.`만 사용한다.
- 2026-07-20 Slack 앱 설정에 변경된 Manifest를 적용했다.
- Manifest 적용 후에도 `auth.test`의 내부 username은 기존 `babgwe`로 반환된다. 이는 봇 표시 이름과 다른 레거시 식별자이므로 코드명 변경 누락으로 취급하지 않는다.
- 최소 권한에 `users:read`가 없어 `bots.info`로 프로필 표시 이름을 재조회할 수 없다. 표시 이름 확인만을 위해 권한을 추가하지 않고 Slack UI에서 확인한다.
- Bot User OAuth Token의 `auth.test`가 성공했다.
- 테스트 채널과 비공개 운영 채널 ID가 로컬 `.env`에 설정되어 있다.
- 2026-07-20 테스트 채널 `C0BJ7DDNTNX`에 `[밥괘 연결 테스트]` 메시지 한 건을 게시했다.
- 테스트 메시지 ID는 `1784523910.088609`이며 `1️⃣`, `2️⃣`, `3️⃣` 반응의 추가와 조회에 성공했다.
- 연결 테스트는 추천 로그를 수정하지 않았다.
- 2026-07-20 같은 테스트 채널에서 전체 일일 작업을 실행해 일반 추천 메시지 `1784524867.270389`를 게시했다.
- 전체 작업은 추천 로그 세 행을 추가했고, 해당 메시지의 `1️⃣`, `2️⃣`, `3️⃣` 반응이 각각 한 개씩 조회됐다.
- 개인 계정으로 `3️⃣`에 반응한 뒤 재실행하여 원본 2개에서 봇 반응을 제외한 좋아요 1개가 Sheet에 기록되고 새 메시지는 게시되지 않는 것을 확인했다.
- 비공개 운영 채널에 테스트임을 명시한 운영 알림 한 건을 보내 `chat:write` 접근을 확인했다.
- 코드와 Manifest를 밥라투스트라로 변경한 뒤 테스트 채널에 `[밥라투스트라 연결 테스트]` 메시지 `1784527032.769259`를 게시했다. 세 번호 반응의 추가와 API 재조회가 성공했고 추천 로그는 변경되지 않았다.
- 발신자 표시 이름과 실제 Slack 화면에서의 문구 인상은 사람이 테스트 메시지를 직접 보고 최종 확인한다.
- 니체를 연상시키는 콧수염과 점심 요소를 결합한 밥라투스트라 캐릭터 아이콘을 Slack 앱 설정에 적용했다. 원본 이미지 파일은 현재 저장소에 없다.
- 저장소 Manifest는 Sheet 링크 버튼을 위해 Socket Mode와 Interactivity가 활성화된 상태다.
- 2026-07-20 변경된 Manifest를 Slack 앱에 적용하고 `connections:write` App-Level Token을 발급했다. 실제 Socket Mode 연결에 성공했으며, Sheet 링크 버튼이 포함된 연결 테스트 메시지 `1784532294.816429` 게시와 세 번호 반응 재조회가 성공했다. 추천 로그는 변경되지 않았다.

## 권한과 토큰

Bot Token Scope는 다음 세 개만 사용한다.

| 권한 | 사용 목적 |
|---|---|
| `chat:write` | 봇이 참여한 점심 채널과 운영 채널에 메시지를 게시한다. |
| `reactions:write` | 게시된 후보에 `1️⃣`, `2️⃣`, `3️⃣` 반응을 추가한다. |
| `reactions:read` | 번호 반응 수를 읽어 추천 로그에 동기화한다. |

다음 권한은 의도적으로 요청하지 않는다.

- `chat:write.public`: 봇을 채널에 직접 초대하는 정책이므로 필요하지 않다.
- `channels:read`: 채널 ID를 환경변수로 직접 설정하므로 필요하지 않다.
- `commands`: 초기에는 Slash Command가 없다.
- 채널 메시지 이력 권한: 초기 반응 조회 방식에는 추가하지 않는다. 실제 Slack API 검증에서 필요성이 확인되면 구현 전에 다시 검토한다.

Socket Mode 서비스에는 Bot User OAuth Token과 별도로 `xapp-`로 시작하는 App-Level Token이 필요하다. App-Level Token에는 `connections:write` scope만 부여한다. 이는 Bot Token Scope가 아니며 Manifest의 `oauth_config.scopes.bot`에 넣지 않는다.

## 앱 생성과 설치

1. [Slack 앱 관리 페이지](https://api.slack.com/apps)에서 `Create New App`을 선택한다.
2. `From an app manifest`를 선택하고 개발할 회사 워크스페이스를 고른다.
3. JSON 형식을 선택하고 `slack/app-manifest.json` 전체를 붙여 넣는다.
4. Slack이 보여주는 앱 이름, 세 가지 Bot Token Scope, Socket Mode와 Interactivity 활성화를 확인한 뒤 앱을 생성한다.
5. `OAuth & Permissions`에서 앱을 워크스페이스에 설치한다.
6. 발급된 `xoxb-` Bot User OAuth Token을 로컬 `.env`의 `SLACK_BOT_TOKEN`에 넣는다. 토큰을 문서, Git, 채팅 또는 화면 캡처에 남기지 않는다.
7. 앱의 `Basic Information`에서 App-Level Token을 만들고 scope는 `connections:write` 하나만 선택한다.
8. 발급된 `xapp-` 토큰을 `.env`의 `SLACK_APP_TOKEN`에 넣는다.

Manifest를 수정해 권한이 바뀌면 앱 설정의 `App Manifest`에도 같은 변경을 적용하고 필요할 경우 워크스페이스에 앱을 다시 설치한다.

## 채널 연결

초기 검증에서는 별도 테스트 채널을 사용한다.

1. 테스트 채널과 비공개 운영 채널을 만든다.
2. 두 채널에서 Slack 자동완성으로 표시 이름 `bapratustra`를 찾아 초대한다. 보이지 않으면 기존 username `babgwe`로 검색하고 Bot User ID `U0BJHC7HXU4`가 맞는지 확인한다.
3. 테스트 채널 ID를 `.env`의 `LUNCH_CHANNEL_ID`에 넣는다.
4. 운영 채널 ID를 `.env`의 `OPS_CHANNEL_ID`에 넣는다.
5. 채널 ID는 Slack 채널 세부 정보나 채널 URL에서 확인한다. 표시 이름이 아니라 `C` 또는 `G`로 시작하는 ID를 사용한다.

실제 운영 전환 때는 직원용 옵트인 채널에도 봇을 초대하고 `LUNCH_CHANNEL_ID`만 운영 채널 ID로 교체한다. 코드나 manifest를 환경별로 복제하지 않는다.

## Socket Mode 서비스

```bash
python -m bapratustra --run-slack-service
```

- 이 프로세스는 `SLACK_APP_TOKEN`과 `SLACK_BOT_TOKEN`만 필요하다.
- `interactive` envelope를 받으면 빈 응답으로 즉시 ACK한다. 현재 버튼 자체의 목적지는 Slack이 여는 Google Sheet URL이다.
- 일반 이벤트를 구독하거나 추천, Sheet 조회와 쓰기를 수행하지 않는다.
- 운영에서는 `deploy/bapratustra-slack.service`로 상시 실행한다.
- App-Level Token이 없거나 Socket Mode가 비활성화되어 있으면 연결할 수 없다.

## 채널 온보딩과 북마크

운영 채널마다 다음을 한 번 수행한다.

1. `LUNCH_CHANNEL_ID`가 대상 채널인지 확인한다.
2. `python -m bapratustra --post-onboarding`을 한 번 실행한다.
3. 게시된 안내 메시지를 Slack에서 고정한다.
4. 채널 북마크에 Google Spreadsheet URL을 `점심 후보와 인기 메뉴`라는 이름으로 추가한다.

고정과 북마크는 일회성 관리 작업이다. 이를 자동화하기 위한 `pins:write`나 `bookmarks:write` 권한은 요청하지 않는다. 명령을 반복하면 안내 메시지가 중복 게시되므로 상태 확인 용도로 사용하지 않는다.

## 연결 테스트 명령

```bash
python -m bapratustra --test-slack
```

- 실제 후보와 추천 로그를 읽어 `[밥라투스트라 연결 테스트]`가 붙은 메시지를 테스트 채널에 한 건 게시한다.
- 일반 정기 게시와 같은 `점심 후보 보태기` 링크 버튼을 포함한다.
- 지도 링크와 미디어의 자동 펼침을 끈다.
- 후보 수만큼 최대 세 개의 번호 반응을 추가하고 `reactions.get`으로 즉시 확인한다.
- 추천 로그에는 행을 추가하지 않는다.
- 성공한 테스트 메시지는 검토 근거로 채널에 남긴다.
- 반복 실행하면 메시지가 추가로 게시되므로 일반적인 상태 확인 명령으로 사용하지 않는다.

## 비밀정보 관리

- `.env`는 Git에서 제외한다.
- Bot Token과 App-Level Token은 로그나 오류 메시지에 포함하지 않는다.
- DGX Spark에서는 `/etc/bapratustra/bapratustra.env`처럼 애플리케이션 저장소 밖의 제한된 환경 파일에 둔다.
- 토큰이 노출되면 종류에 맞게 Slack 앱 설정에서 즉시 폐기·재발급 또는 재설치하고 서버 값을 교체한다.
- 토큰 값 자체를 인계 문서에 적지 않고 후임자가 Slack 앱 설정과 서버 비밀정보에 접근할 수 있게 한다.

## 인턴 종료 전 인계

- 정직원 후임자를 Slack 앱의 관리 가능한 협업자로 추가한다.
- 후임자 계정으로 앱 설정, OAuth 권한과 재설치 기능에 접근 가능한지 확인한다.
- 후임자가 테스트 채널과 비공개 운영 채널을 관리할 수 있는지 확인한다.
- 후임자가 DGX Spark의 환경 파일을 교체하고 서비스를 재시작할 수 있는지 확인한다.
- 인계 검증 후 최초 개발자의 Slack 앱 관리 권한을 제거한다.

## 저장소 밖에서 관리하는 실제 값

- 테스트 채널 ID, 비공개 운영 채널 ID, Bot User OAuth Token과 App-Level Token은 로컬 `.env`에만 둔다.
- 향후 실제 직원용 옵트인 채널 ID는 채널 생성 후 `LUNCH_CHANNEL_ID`에 설정한다.
