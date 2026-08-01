# Basic Concepts

The building blocks of the Messages API, each script isolating one concept.
No shared library code yet — every file defines its own minimal
`MessageList` so the mechanics are visible end to end.

| File | Concept |
| --- | --- |
| `001_requests.py` | A single `messages.create` call and the request/response shape. |
| `002_looping.py` | Turning single calls into a multi-turn conversation loop (a REPL). |
| `003_system_prompt.py` | Steering behavior with a `system` prompt (a Socratic math tutor). |
| `004_system_prompt_ex.py` | A second system prompt example, with a mistake left in on purpose — two `SYSTEM_PROMPT` assignments, only the second takes effect. |
| `005_temperature.py` | Comparing `temperature=0.0` (near-deterministic) vs. `temperature=1.0` (creative) on the same prompt. |
| `006_streaming.py` | Streaming responses token-by-token with `messages.stream` instead of waiting for the full response. |
| `007_structured_data.py` | Constraining output format via assistant-message prefill + `stop_sequences`, rather than asking nicely in the prompt. |

Run any file directly, e.g.:

```bash
uv run python -m src.basic_concepts.001_requests
```
