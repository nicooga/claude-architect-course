# Prompt Engineering

Treats prompts as something you test and score, not just write. Builds a
small evaluation pipeline: generate a dataset of tasks, run a prompt against
each, and grade the results both mechanically and by another model call.

- `generate_dataset.py` — uses Claude to generate `dataset.data.json`, a set
  of tasks that each require a Python function, a JSON object, or a regex to
  solve.
- `evaluation_pipeline.py` — for each task: runs the prompt under test
  (`run_prompt`), checks the output actually parses for its target format
  (`grade_by_syntax`), and has a model grade it 1–10 on quality
  (`grade_by_model`, with retry-on-malformed-JSON). Writes
  `evaluation_results.data.json` with per-task scores and an average.
- `dataset.data.json` / `evaluation_results.data.json` — generated
  artifacts from running the scripts above, worked examples left on disk.
  Gitignored (`**/*.data.*`) rather than checked in — regenerate them
  locally instead of expecting them in a fresh checkout.

This is the first unit to depend on `lib/ai_generation` instead of a local
`MessageList`.

Run with:

```bash
uv run python -m src.prompt_engineering.generate_dataset
uv run python -m src.prompt_engineering.evaluation_pipeline
```
