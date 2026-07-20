# 밥괘

매일 평일 오전 11시(KST), 사내 Slack 채널에 세 곳의 점심 후보를 알려주는 봇이다. 후보는 직원들이 공동 편집하는 Google Sheet에서 가져온다.

현재 저장소는 **초기 구현 단계**다. 설정 검증, 순수 추천 로직, 메시지 포맷, Google Sheets 후보와 추천 로그의 읽기·검증, 추천 로그 일괄 추가 함수와 systemd 템플릿이 있다. Slack 게시와 전체 일일 작업 연결은 아직 구현하지 않았다. 따라서 `deploy/`의 unit을 서버에서 활성화하면 안 된다.

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
python -m babgwe
```

이 명령은 외부 API를 호출하지 않고 전체 설정만 검증한다. Slack 설정 전에도 실제 Google Sheet의 읽기와 추천 미리보기를 확인할 수 있다.

```bash
python -m babgwe --dry-run
```

드라이런은 후보와 추천 로그를 모두 읽어 공정 순환 추천을 계산하지만 Sheet를 수정하거나 Slack 메시지를 보내지 않는다. 유효 후보가 없으면 연결 성공을 출력한 뒤 종료 코드 `1`을 반환한다.

## 테스트

```bash
pytest
```

## 문서

작업 전에는 반드시 `AGENTS.md`를 먼저 읽는다. 제품 범위, 데이터 스키마, 기능 및 운영 결정은 `docs/README.md`에서 찾을 수 있다.
