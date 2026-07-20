# Google 자원 소유권과 인계

## 목표

밥라투스트라의 Google Sheet, Cloud 프로젝트와 Service Account가 최초 개발자의 개인 계정에 종속되지 않게 한다. 최초 개발자가 조직을 떠나도 운영 담당자가 접근 권한을 복구하고 인증 정보를 교체할 수 있어야 한다.

## 현재 결정

- 회사는 Google Workspace와 Shared Drive를 사용하지 않는다.
- 최초 개발 기간에는 개발자의 개인 Google 계정으로 Sheet와 Google Cloud 프로젝트를 만든다.
- 인턴 종료 전 Sheet 소유권과 Cloud 프로젝트 관리 권한을 정직원 후임자에게 넘긴다.
- 공용 계정이나 공동 비밀번호는 만들지 않는다.

## 현재 생성된 자원

| 항목 | 현재 값 |
|---|---|
| 최초 소유 계정 | `mistervic03@gmail.com` |
| Google Cloud 프로젝트 이름 | `Bapratustra Lunch Bot` |
| Google Cloud 프로젝트 ID | `babgwe-lunch-bot` |
| Service Account | `babgwe-bot@babgwe-lunch-bot.iam.gserviceaccount.com` |
| Google Sheet | [밥라투스트라 점심 추천](https://docs.google.com/spreadsheets/d/1pyOGBbDwAZurNSTY0foQmTg7mojEGhYD3DzMal-WeSc/edit) |
| Spreadsheet ID | `1pyOGBbDwAZurNSTY0foQmTg7mojEGhYD3DzMal-WeSc` |

Google Cloud 프로젝트 ID, Service Account 이메일, Spreadsheet ID와 기존 로컬 인증 파일 경로는 브랜드 변경 전 생성된 외부 식별자다. 프로젝트와 Sheet의 표시 이름은 변경했지만 이 안정적인 식별자들은 재생성이나 이동의 실익이 없어 그대로 유지한다. 이후 작업자는 옛 이름이 보인다는 이유만으로 프로젝트나 Service Account를 새로 만들거나 인증 파일을 이동하지 않는다.

- Cloud 프로젝트에는 Google Sheets API와 Google Drive API가 활성화되어 있다.
- 애플리케이션 런타임은 Sheets API만 사용한다. Drive API는 초기 Sheet 생성과 Service Account 공유를 CLI로 처리하기 위해 활성화했다.
- Service Account는 현재 Sheet의 편집자로 공유되어 있다.
- 로컬 개발 키는 `/Users/sin-yejoon/.config/babgwe/google-service-account.json`에 있으며 파일 권한은 `600`이다.
- 키 파일은 저장소에 포함하지 않는다. DGX Spark 배포 때는 새 서버 경로와 권한을 별도로 설정한다.

## 현재 구성

```text
최초 개발자의 개인 Google 계정
├── 밥라투스트라 Google Sheet
└── 밥라투스트라 Google Cloud 프로젝트
    └── 밥라투스트라 전용 Service Account

인계 후
├── 정직원 후임자 Google 계정: Sheet 소유자와 Cloud 프로젝트 관리자
├── 백업 담당자 Google 계정: 가능하면 편집 및 관리 권한 보유
└── 최초 개발자 계정: 최종 검증 후 권한 제거
```

- 점심봇 전용 Service Account를 하나만 만들고 대상 Spreadsheet에만 편집 권한을 부여한다.
- 직원 공동 편집은 각 직원의 Google 계정에 Sheet 편집 권한을 공유하는 방식으로 운영한다.
- 단순 편집자 공유는 소유권 인계가 아니다. 후임자가 소유권 이전 요청을 실제로 수락해야 한다.

## Sheet 소유권 이전 제약

- 최초 개발자와 후임자가 모두 개인 Google 계정이면 파일을 먼저 공유한 후 소유권 이전을 요청할 수 있다.
- 개인 Google 계정이 소유한 파일을 회사 또는 학교 Workspace 계정으로 직접 이전할 수 없다.
- 후임자가 Workspace 계정을 사용한다면 현재 Sheet를 복사해 후임자 계정 소유의 새 Sheet를 만들고 Spreadsheet ID와 Service Account 공유를 다시 설정해야 한다.
- 소유권 이전 후 파일은 새 소유자의 저장 용량에 포함된다.
- 이전 요청이 수락되기 전까지는 최초 개발자가 소유자이므로 마지막 근무일까지 미루지 않는다.

## Cloud IAM 인계

Service Account는 만든 개인 계정으로 로그인해 실행되는 것은 아니지만, 이를 포함한 Cloud 프로젝트를 관리할 정직원 계정이 반드시 남아야 한다.

- 후임자에게 프로젝트의 전체 운영과 추가 인계를 수행할 수 있는 관리 권한을 부여하고, 후임자 계정으로 접근 가능한지 확인한 뒤 최초 개발자의 권한을 제거한다.
- 최소 한 명, 가능하면 두 명의 정직원에게 프로젝트 관리 권한을 부여한다.
- Service Account의 생성, 비활성화, 키 교체가 필요한 담당자에게 `Service Account Admin` 역할을 부여한다.
- 거의 모든 권한이 필요한 경우가 아니라면 편의를 이유로 `Owner` 역할을 넓게 부여하지 않는다. 회사의 기존 Cloud 운영 정책과 역할 분담을 우선한다.
- 서버의 JSON 키 파일은 저장소나 메신저에 올리지 않는다. 제한된 서버 경로에 설치하고 운영 담당자가 교체 절차를 알 수 있게 한다.
- 인계가 끝나면 후임 담당자 계정으로 Cloud Console 접근, Service Account 확인, 새 키 발급 가능 여부를 직접 확인한다.

## 인턴 종료 전 체크리스트

1. 후임자 Google 계정이 개인 계정인지 Workspace 계정인지 확인한다.
2. 개인 계정이면 Sheet 소유권 이전을 요청하고 후임자가 수락했는지 확인한다.
3. Workspace 계정이라 직접 이전할 수 없으면 후임자가 복사본을 소유하게 하고 새 Spreadsheet ID로 설정을 바꾼다.
4. 직원과 Service Account가 최종 Sheet에 필요한 편집 권한을 갖는지 확인한다.
5. 정직원 후임자에게 필요한 Cloud 프로젝트와 Service Account 관리 권한을 부여한다.
6. 후임자 계정으로 Cloud Console 접근과 새 Service Account 키 발급 가능 여부를 확인한다.
7. DGX Spark에서 최종 Sheet의 실제 읽기·쓰기를 확인한다.
8. Slack 앱 관리 권한도 정직원 후임자에게 추가한다.
9. 후임자 단독으로 운영과 복구가 가능함을 확인한 뒤 최초 개발자의 권한을 제거한다.

## 현재 확인이 필요한 항목

- 후임자의 Google 계정은 개인 계정인가, Workspace 계정인가?
- 장기 운영 담당자와 백업 담당자는 누구인가?
- 실제 인계와 검증을 완료할 날짜는 언제인가?
