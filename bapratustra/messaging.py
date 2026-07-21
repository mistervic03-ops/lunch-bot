from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from bapratustra.recommendation import LunchOption


NUMBER_REACTIONS = ("one", "two", "three")
KST = ZoneInfo("Asia/Seoul")
OPEN_CANDIDATE_WEB_ACTION_ID = "open_candidate_web"
OPEN_LEADERBOARD_ACTION_ID = "open_leaderboard"
DECLARATION_EPOCH = date(2026, 7, 20)
DAILY_DECLARATIONS = (
    (
        "점심은 스스로 정해지지 않는다. 선택되어야 한다.\n"
        "오늘 그대들 앞에는 세 갈래의 길이 놓여 있다."
    ),
    "오늘의 점심은 아직 정해지지 않았다.\n다만 세 가지 가능성이 여기 있다.",
    "정오는 다가오고, 결단의 시간도 함께 온다.\n오늘의 길은 셋이다.",
    (
        "배고픔 앞에서 망설임은 길어지고 점심시간은 짧아진다.\n"
        "오늘의 후보는 셋이다."
    ),
    "오늘의 깨달음은 멀리 있지 않다.\n점심은 이 세 곳 중 하나에 있다.",
    (
        "무엇을 먹을 것인가. 그것이 오늘의 가장 현실적인 물음이다.\n"
        "세 가지 답을 가져왔다."
    ),
    (
        "허기는 매일 돌아오지만, 같은 선택을 반복할 이유는 없다.\n"
        "오늘의 세 갈래 길을 보라."
    ),
)


@dataclass(frozen=True)
class SlackPost:
    channel_id: str
    message_ts: str


def _daily_declaration(run_date_kst: date) -> str:
    days = (run_date_kst - DECLARATION_EPOCH).days
    weeks, remainder = divmod(days, 7)
    weekday_number = weeks * 5 + min(remainder, 5)
    return DAILY_DECLARATIONS[weekday_number % len(DAILY_DECLARATIONS)]


def build_daily_message(
    recommendations: Sequence[LunchOption], *, run_date_kst: date | None = None
) -> str:
    """Build the compact single-message format agreed for the daily post."""
    if not recommendations:
        raise ValueError("daily messages require at least one recommendation")

    if len(recommendations) == 1:
        introduction = "오늘 확인된 점심의 운명은 하나뿐이다."
    elif len(recommendations) == 2:
        introduction = "오늘 보이는 점심의 길은 둘뿐이다."
    else:
        message_date = run_date_kst or datetime.now(KST).date()
        introduction = _daily_declaration(message_date)

    lines = [
        "📜 밥라투스트라는 이렇게 말했다.",
        "",
        introduction,
        "",
    ]
    for index, option in enumerate(recommendations, start=1):
        details = [option.menu]
        if option.price is not None:
            details.append(f"{option.price:,}원")
        if option.recommended_by:
            details.append(f"추천: {option.recommended_by}")
        line = f"{index}. {option.restaurant} — {' · '.join(details)}"
        if option.map_url:
            line += f" <{option.map_url}|지도>"
        lines.append(line)

    lines.append("")
    if len(recommendations) < 3:
        lines.append("새 후보는 아래 버튼에서 등록할 수 있습니다.")
    else:
        lines.append("먹고 싶은 후보 번호에 반응해 주세요.")
    return "\n".join(lines)


def _message_blocks(
    text: str, candidate_url: str, leaderboard_url: str
) -> list[dict[str, Any]]:
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "식당·메뉴 등록",
                        "emoji": True,
                    },
                    "url": candidate_url,
                    "action_id": OPEN_CANDIDATE_WEB_ACTION_ID,
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "전당 보기",
                        "emoji": True,
                    },
                    "url": leaderboard_url,
                    "action_id": OPEN_LEADERBOARD_ACTION_ID,
                }
            ],
        },
    ]


def build_onboarding_message() -> str:
    """Build the stable channel guide intended to be pinned once."""
    return (
        "📜 밥라투스트라의 점심 채널에 오신 것을 환영합니다.\n\n"
        "평일 오전 11시(KST)에 점심 후보 세 곳을 올립니다.\n"
        "먹고 싶은 후보 번호의 1️⃣, 2️⃣, 3️⃣ 반응을 눌러 주세요. "
        "여러 곳을 골라도 됩니다.\n"
        "새 후보는 아래 버튼에서 등록할 수 있고, 누적 좋아요와 순위는 "
        "‘밥라투스트라의 전당’에서 확인할 수 있습니다."
    )


def post_daily_message(
    client: Any,
    channel_id: str,
    recommendations: Sequence[LunchOption],
    *,
    candidate_url: str,
    leaderboard_url: str,
    run_date_kst: date | None = None,
    connection_test: bool = False,
) -> SlackPost:
    """Post one compact message without expanding map links into previews."""
    text = build_daily_message(recommendations, run_date_kst=run_date_kst)
    if connection_test:
        text = f"[밥라투스트라 연결 테스트]\n\n{text}"
    response = client.chat_postMessage(
        channel=channel_id,
        text=text,
        blocks=_message_blocks(text, candidate_url, leaderboard_url),
        unfurl_links=False,
        unfurl_media=False,
    )
    posted_channel = str(response.get("channel", "")).strip()
    message_ts = str(response.get("ts", "")).strip()
    if not posted_channel or not message_ts:
        raise RuntimeError("Slack post response must include channel and ts")
    return SlackPost(channel_id=posted_channel, message_ts=message_ts)


def post_channel_onboarding(
    client: Any,
    channel_id: str,
    *,
    candidate_url: str,
    leaderboard_url: str,
) -> SlackPost:
    """Post the one-time channel guide; pinning remains a manual admin action."""
    text = build_onboarding_message()
    response = client.chat_postMessage(
        channel=channel_id,
        text=text,
        blocks=_message_blocks(text, candidate_url, leaderboard_url),
        unfurl_links=False,
        unfurl_media=False,
    )
    posted_channel = str(response.get("channel", "")).strip()
    message_ts = str(response.get("ts", "")).strip()
    if not posted_channel or not message_ts:
        raise RuntimeError("Slack post response must include channel and ts")
    return SlackPost(channel_id=posted_channel, message_ts=message_ts)


def pin_message(client: Any, post: SlackPost) -> None:
    """Pin a message that the bot has already posted to its channel."""
    client.pins_add(channel=post.channel_id, timestamp=post.message_ts)


def add_candidate_reactions(
    client: Any, channel_id: str, message_ts: str, count: int
) -> tuple[str, ...]:
    """Seed the functional number reactions that map to candidate positions."""
    if count < 1 or count > len(NUMBER_REACTIONS):
        raise ValueError("candidate reaction count must be between 1 and 3")
    reaction_names = NUMBER_REACTIONS[:count]
    for name in reaction_names:
        client.reactions_add(channel=channel_id, timestamp=message_ts, name=name)
    return reaction_names


def get_reaction_counts(
    client: Any, channel_id: str, message_ts: str
) -> dict[str, int]:
    """Return Slack's raw counts, including the bot's seeded reactions."""
    response = client.reactions_get(
        channel=channel_id, timestamp=message_ts, full=True
    )
    reactions = response.get("message", {}).get("reactions", [])
    return {
        str(reaction.get("name", "")): int(reaction.get("count", 0))
        for reaction in reactions
        if reaction.get("name")
    }


def post_ops_alert(
    client: Any,
    channel_id: str,
    *,
    stage: str,
    outcome: str,
    error_id: str | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Post a concise operational alert without exception or credential details."""
    alert_time = occurred_at or datetime.now(tz=KST)
    if alert_time.tzinfo is None or alert_time.utcoffset() is None:
        raise ValueError("occurred_at must include timezone information")
    lines = [
        "밥라투스트라 운영 알림",
        f"발생 시각: {alert_time.astimezone(KST):%Y-%m-%d %H:%M:%S} KST",
        f"단계: {stage}",
        f"결과: {outcome}",
    ]
    if error_id:
        lines.append(f"오류 ID: {error_id}")
    client.chat_postMessage(
        channel=channel_id,
        text="\n".join(lines),
        unfurl_links=False,
        unfurl_media=False,
    )
