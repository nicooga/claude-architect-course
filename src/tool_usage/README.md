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

By the end, Claude should handle a natural language request like "remind me
in a week" by chaining these tools together: get the current time, compute
the target time, then set the reminder.

## Principle

When the model has a limitation, extend it with tools rather than trying to
prompt your way around the limitation.
