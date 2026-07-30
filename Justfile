# List available recipes
default:
    @just --list

# Type-check the project (same engine and config as Pylance in VS Code)
typecheck:
    @uv run pyright

# List available Anthropic model IDs
models:
    @curl -s https://api.anthropic.com/v1/models?limit=100 \
        -H 'anthropic-version: 2023-06-01' \
        -H "X-Api-Key: $ANTHROPIC_API_KEY" \
        | jq -r '.data[].id'

# Show which models accept an assistant-message prefill.
# The /v1/models capabilities tree has no prefill field, so this probes each
# model with a one-token prefilled request and reports whether it 400s.
models-prefill:
    #!/usr/bin/env bash
    set -euo pipefail
    for m in $(just models); do
        body=$(jq -nc --arg m "$m" '{
            model: $m, max_tokens: 1,
            messages: [{role:"user",content:"hi"},{role:"assistant",content:"{"}]
        }')
        verdict=$(curl -s https://api.anthropic.com/v1/messages \
            -H 'anthropic-version: 2023-06-01' \
            -H "X-Api-Key: $ANTHROPIC_API_KEY" \
            -H 'content-type: application/json' \
            -d "$body" \
            | jq -r 'if .type == "error" then "no  (" + .error.message + ")" else "yes" end')
        printf '%-28s %s\n' "$m" "$verdict"
    done
