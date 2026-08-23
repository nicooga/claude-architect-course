# MCP Reminders Server — Bruno collection

A raw JSON-RPC-over-HTTP collection for talking to
[`src/mcp_server/server.py`](../../src/mcp_server/server.py) directly, no MCP
client library involved — useful for seeing the protocol itself rather than
what a `ClientSession` does with it.

## Setup

1. Start the server over streamable HTTP:
   ```bash
   uv run python src/mcp_server/server.py streamable-http
   ```
   Runs on `127.0.0.1:8000/mcp` by default. Going through the **Ngrok Tunnel**
   environment instead of Local? Set `MCP_ALLOW_ANY_HOST=1` first:
   ```bash
   MCP_ALLOW_ANY_HOST=1 uv run python src/mcp_server/server.py streamable-http
   ```
   Binding `127.0.0.1` auto-enables DNS-rebinding protection (only
   `Host`/`Origin` headers naming localhost are accepted), and a tunnel
   forwards the request's original public hostname — see the comment above
   `MCP_ALLOW_ANY_HOST` in `server.py`'s `__main__` for the full story. Same
   fix `003_mcp_transports.py` needed for the same reason.
2. Open this folder as a collection in Bruno.
3. Pick an environment (top right): **Local** (`http://127.0.0.1:8000`) or
   **Ngrok Tunnel** — edit that one's `baseUrl` to your current tunnel URL
   each time it changes (`ngrok http 8000`, or whatever `003_mcp_transports.py`
   printed).

## Running it

Run **01 - Initialize** first — its post-response script captures the
`Mcp-Session-Id` response header into a collection variable, and every
request after it sends that header back. Skip it and the later requests get
rejected: this server is session-based (`stateless_http=False`), not stateless.

After that, the requests can be run in order or individually:

| # | Request | Primitive |
| - | --- | --- |
| 01 | Initialize | handshake |
| 02 | Initialized Notification | handshake (no response expected) |
| 03 | Tools List | tools — model-controlled |
| 04 | Tools Call — list_reminders | tools |
| 05 | Tools Call — set_reminder | tools |
| 06 | Resources List | resources — application-controlled |
| 07 | Resources Read — reminders://all | resources |
| 08 | Prompts List | prompts — user-controlled |
| 09 | Prompts Get — review_reminders | prompts |

## One thing that'll look odd at first

Response bodies come back **SSE-framed**, not plain JSON:

```
event: message
data: {"jsonrpc":"2.0","id":3,"result":{...}}
```

That's `run_streamable_http_async(json_response=False)`, the server's
default — each POST gets a one-shot event stream carrying the JSON-RPC
response, not a bare JSON body. Bruno shows it as raw text rather than
pretty-printing it; the payload is the `data:` line.

## See also

`src/mcp_server/README.md`'s manual test script covers the same primitives
through the official MCP Inspector — this collection is the same checks with
the wire format visible instead of a client library hiding it.
