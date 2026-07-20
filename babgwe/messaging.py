from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from babgwe.recommendation import LunchOption


NUMBER_REACTIONS = ("one", "two", "three")
KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class SlackPost:
    channel_id: str
    message_ts: str


def build_daily_message(recommendations: Sequence[LunchOption]) -> str:
    """Build the compact single-message format agreed for the daily post."""
    if not recommendations:
        raise ValueError("daily messages require at least one recommendation")

    lines = ["🔮 오늘의 밥괘가 나왔습니다."]
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

    if len(recommendations) < 3:
        lines.append(
            "후보가 조금 부족해요. 시트에 새로운 밥괘를 더해주세요."
        )
    return "\n".join(lines)


def post_daily_message(
    client: Any,
    channel_id: str,
    recommendations: Sequence[LunchOption],
    *,
    connection_test: bool = False,
) -> SlackPost:
    """Post one compact message without expanding map links into previews."""
    text = build_daily_message(recommendations)
    if connection_test:
        text = f"[밥괘 연결 테스트]\n\n{text}"
    response = client.chat_postMessage(
        channel=channel_id,
        text=text,
        unfurl_links=False,
        unfurl_media=False,
    )
    posted_channel = str(response.get("channel", "")).strip()
    message_ts = str(response.get("ts", "")).strip()
    if not posted_channel or not message_ts:
        raise RuntimeError("Slack post response must include channel and ts")
    return SlackPost(channel_id=posted_channel, message_ts=message_ts)


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
        "밥괘 운영 알림",
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
