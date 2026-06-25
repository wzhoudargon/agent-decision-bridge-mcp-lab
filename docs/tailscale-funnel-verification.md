# Tailscale Funnel Verification

Date: 2026-06-21

Latest stable connector verification: 2026-06-22

Scope: stable public URL path for Decision Inbox MCP v1 without a user-owned
domain.

## Result

Status: local and public smoke verification complete. Public exposure was
disabled after verification.

ChatGPT Web stable connector verification with OAuth Owner password also
completed on 2026-06-22. ChatGPT connected to the stable Tailscale endpoint,
completed OAuth approval, read the prepared package, and submitted advice back
to the expected task advice folder.

Stable public origin:

```text
https://your-device.example-tailnet.ts.net
```

Public MCP endpoint:

```text
https://your-device.example-tailnet.ts.net/mcp
```

Local backend:

```text
http://127.0.0.1:8765
```

## Setup Used

Tailscale CLI was installed through Homebrew formula `tailscale`.

The macOS cask installer was not used because it requires an interactive sudo
password and system extension approval. Instead, this run used a project-scoped
userspace daemon:

```bash
tailscaled \
  --tun=userspace-networking \
  --socket=/tmp/tailscaled-decision-inbox.sock \
  --statedir="$HOME/.local/share/tailscale-decision-inbox"
```

Tailscale login was completed by the user in the browser.

Initial local/public smoke used bearer-token compatibility auth:

```bash
DECISION_INBOX_MCP_TOKEN="<redacted-temporary-token>" \
DECISION_INBOX_PUBLIC_BASE_URL="https://your-device.example-tailnet.ts.net" \
python3 server/decision_inbox_http_server.py --host 127.0.0.1 --port 8765
```

The ChatGPT Web stable connector verification used OAuth Owner password auth:

```bash
openssl rand -base64 32 > /tmp/decision-inbox-oauth-owner-token
chmod 600 /tmp/decision-inbox-oauth-owner-token

DECISION_INBOX_OAUTH_OWNER_TOKEN="$(cat /tmp/decision-inbox-oauth-owner-token)" \
DECISION_INBOX_PUBLIC_BASE_URL="https://your-device.example-tailnet.ts.net" \
python3 server/decision_inbox_http_server.py --host 127.0.0.1 --port 8765
```

Funnel was enabled with:

```bash
tailscale --socket=/tmp/tailscaled-decision-inbox.sock funnel --bg --yes 8765
```

## Verification

Funnel status:

```text
https://your-device.example-tailnet.ts.net (Funnel on)
|-- / proxy http://127.0.0.1:8765
```

No-token public GET:

```text
HTTP/2 401
WWW-Authenticate: Bearer
```

Token-authenticated public JSON-RPC `tools/list`:

```text
with_token_status=ok
tools=list_decision_tasks,get_decision_package,submit_advice,request_local_fact_check,get_task_status
```

Current 2026-06-23 Auto MCP scope update: `request_local_fact_check` is no
longer exposed as a default Auto MCP web tool. New preflight runs should expect:

```text
tools=list_decision_tasks,get_decision_package,submit_advice,get_task_status
```

OAuth ChatGPT Web connector result on 2026-06-22:

```text
app=Decision Inbox Lab Temp
auth=OAuth Owner password
task=stable-tailscale-connector-verification
advice=advice/2026-06-22T07-25-45Z-chatgpt-web-stable-tailscale-connector.md
import_command=python3 scripts/import_advice_review.py stable-tailscale-connector-verification
```

Negative checks:

```text
bad_task_is_error=True
bad_task_message=Access denied: Task id must be a lowercase slug using letters, numbers, and hyph
unknown_tool_is_error=True
unknown_tool_message=Unknown tool: run_shell
```

## Risk

Active Funnel risk coefficient: `3/5`.

Reasons:

- The endpoint is publicly reachable.
- Bearer-token authentication is required.
- The server exposes only Decision Inbox package/advice/status tools.
- No shell, Git, dependency installation, arbitrary read, arbitrary write, or
  real project workspace tools are exposed.

Public scanner traffic was observed within minutes of opening Funnel. Requests
included common probes such as:

```text
/
/.env
/.git/config
/server-status
/wp-json/
/xmlrpc.php
```

The Decision Inbox server returned `404` or `401` for these paths. No project
files or secrets were exposed, but this confirms the endpoint should not be left
open longer than needed for a connector test.

Post-verification state:

```text
Funnel disabled
Local MCP server stopped
Temporary token or Owner password deleted
Risk coefficient: 1/5
```

Stop commands:

```bash
tailscale --socket=/tmp/tailscaled-decision-inbox.sock funnel reset
```

Then stop the local MCP server and remove the temporary token or Owner password:

```bash
rm -f /tmp/decision-inbox-mcp-token
rm -f /tmp/decision-inbox-oauth-owner-token
```

To stop the userspace daemon, interrupt the `tailscaled` session or terminate the
matching process.
