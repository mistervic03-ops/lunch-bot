from __future__ import annotations

from collections.abc import Sequence

from babgwe.recommendation import LunchOption


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
