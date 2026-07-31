# Tool Usage

## Goal

Build a practical project that teaches Claude how to set reminders for future
dates. The target interaction is simple:

> "Set a reminder for my doctor's appointment. It's a week from Thursday."
>
> "OK, I will remind you."

Getting there means solving three gaps between what Claude can do naturally
and what this task needs:

1. **Limited time awareness** — Claude may know today's date but not the
   exact current time.
2. **Date calculation issues** — Claude isn't reliable at date/time
   arithmetic, especially for dates further out.
3. **No reminder capability** — Claude has no built-in way to actually set a
   reminder.

Tools are how we close each gap.

## Tools to build

We'll add these one at a time, in order of increasing complexity, so we
understand tool calling before combining tools into a workflow:

1. **Get the current date time** — precise time awareness.
2. **Add duration to date time** — reliable date arithmetic, offloaded from
   the model.
3. **Set a reminder** — the actual side effect: recording the reminder in
   the system.
4. **Text editor** — Anthropic's built-in, schema-less `str_replace_based_edit_tool`.
   Unlike the tools above, Claude already knows its input shape server-side;
   our job is only to execute `view`/`create`/`str_replace`/`insert` against
   a configured working directory, confining every operation to it.

By the end, Claude should handle a natural language request like "remind me
in a week" by chaining these tools together: get the current time, compute
the target time, then set the reminder.

## Principle

When the model has a limitation, extend it with tools rather than trying to
prompt your way around the limitation.

## Testing the REPL

Make sure `ANTHROPIC_API_KEY` is set (e.g. `source .envrc` if you use direnv),
then run the smoke test as a module so `src.tool_usage.tools` resolves:

```bash
uv run python -m src.tool_usage.repl_smoke_test
```

Things to try at the `?>` prompt:

- `What time is it right now, in UTC?` — should trigger the
  `get_current_datetime` tool and answer with the real current time.
- `What is 2+2?` — should answer directly, with no tool call.
- Ask a follow-up in the same session (e.g. `What did I just ask you?`) to
  confirm conversation history survives a tool-using turn.
- `Set a reminder for my doctor's appointment. It's a week from Thursday.`
  — should chain all three tools: `get_current_datetime` to establish
  "now", `add_duration_to_datetime` to compute the target date, then
  `set_reminder` to record it.
- `Create a file named notes.txt in your working directory with a haiku
  about testing.` — should trigger the text editor tool's `create` command.
  The smoke test prints the temp directory it's using at startup, so you can
  inspect the file afterward.
- Ask it to view or edit an existing file in that directory (create one by
  hand first, or ask Claude to) — should chain `view` then `str_replace`.

Press Ctrl+D or Ctrl+C to exit.
