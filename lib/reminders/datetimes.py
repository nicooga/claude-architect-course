"""The two date operations the reminder flow needs, as plain functions.

Stage 3 names three gaps between what Claude does naturally and what "remind
me a week from Thursday" requires: it has no precise clock, it is unreliable
at date arithmetic, and it cannot record anything. The first two are closed
here and the third in `store.py` — kept as functions rather than baked into
the tool classes so the Stage 3 `ToolPort` tools and the Stage 5 MCP server
call the same code and cannot drift apart.
"""

from datetime import datetime, timedelta, timezone


def now_iso(utc_offset_hours: float) -> str:
    """The current instant, ISO 8601, expressed at the given UTC offset.

    No default: "now" should mean the caller's clock, not Greenwich's, and
    "today"/"tomorrow" depend on the local calendar day, which UTC and a
    user's offset can disagree about at any given moment. This module is
    shared by the Stage 3 local tools and the Stage 5 MCP server, and the
    server has no legitimate way to know a caller's timezone on its own —
    so the offset always has to come in from outside, not be guessed here.
    See `src/tool_usage/tools/get_user_utc_offset.py` for how a client
    discovers the value in the first place.
    """
    tz = timezone(timedelta(hours=utc_offset_hours))
    return datetime.now(tz).isoformat()


def add_duration(
    start: str,
    weeks: float = 0,
    days: float = 0,
    hours: float = 0,
    minutes: float = 0,
) -> str:
    """Offsets an ISO 8601 datetime and returns the result, also ISO 8601.

    Raises ValueError if `start` is not parseable — the caller decides
    whether that surfaces as a tool error or a protocol error.
    """
    return (
        datetime.fromisoformat(start)
        + timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes)
    ).isoformat()
