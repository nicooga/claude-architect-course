from datetime import datetime
from typing import Any, Dict


class GetUserUTCOffsetTool:
    """The one piece of ground truth that has to come from the client, not
    the reminders domain: what timezone is the user actually in. Deliberately
    not part of `lib/reminders` or the Stage 5 MCP server — a server has no
    legitimate way to know what machine its caller is on, and guessing from
    its own host OS is only an accident of stdio colocating client and
    server today. This tool reads the OS timezone of whichever machine runs
    *this* process, which for every entrypoint in this repo so far is the
    user's own. Implements ToolPort structurally — no inheritance needed.
    """

    name = "get_user_utc_offset"
    description = (
        "Returns the user's local UTC offset in hours (e.g. -3 for "
        "Argentina), read from this client machine's own clock. Call this "
        "before get_current_datetime whenever you don't already know the "
        "user's timezone from earlier in the conversation — "
        "get_current_datetime has no default and always requires an "
        "explicit offset."
    )
    input_schema: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    async def execute(self, tool_input: Dict[str, Any]) -> str:
        # datetime.now() is naive; .astimezone() with no argument is what
        # attaches this machine's own system timezone to it, DST included.
        offset = datetime.now().astimezone().utcoffset()
        assert offset is not None  # always set once astimezone() has run
        return str(offset.total_seconds() / 3600)
