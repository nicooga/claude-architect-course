# List available recipes
default:
    @just --list

# List available Anthropic model IDs
models:
    @curl -s https://api.anthropic.com/v1/models?limit=100 \
        -H 'anthropic-version: 2023-06-01' \
        -H "X-Api-Key: $ANTHROPIC_API_KEY" \
        | jq -r '.data[].id'
