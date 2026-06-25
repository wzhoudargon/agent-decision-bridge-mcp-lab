# Agent Decision Bridge Connector Runbook

This runbook captures the connector hygiene for Manual Package, Read-Only
Project Advisor, and the explicit high-risk Full-Agent Execution mode.

## Principle

Read-Only Project Advisor borrows the self-hosted connector shape and limited
project reading, not write or shell permissions.

Safe to borrow:

- local MCP server,
- public HTTPS tunnel or reverse proxy,
- public base URL configured as an origin,
- Host header allowlist derived from that public URL,
- OAuth Owner password approval for stable ChatGPT connector runs,
- short-lived bearer token only for temporary/local compatibility tests,
- explicit preflight, shutdown, and cleanup checks.

Not borrowed in Read-Only Project Advisor:

- file writes,
- shell commands,
- Git operations,
- dependency installation,
- direct secret/key/token reads,
- automatic execution of advisor advice.

Full-Agent mode intentionally borrows the broad workspace shape. It must be
started explicitly with `--mode full-agent`, requires `--allowed-root`, and is
always risk `5/5`.

## Product Tiers And Connectors

Use separate ChatGPT account-side connectors:

| Product tier | CLI mode | OAuth scope | ChatGPT connector |
|---|---|---|---|
| Manual Package | `manual` | none | none |
| Legacy Auto MCP Package | `auto-mcp` | `decision-inbox` | one package-only compatibility connector |
| Read-Only Project Advisor | `read-only-project` | `read-only-project` | one read-only project connector |
| Full-Agent Execution | `full-agent` | `full-agent` | one separate execution connector |

Do not reuse a single ChatGPT app for Read-Only Project Advisor and Full-Agent.
It creates stale scope/tool-cache ambiguity and makes it unclear whether a
conversation has read-only advisor access or execution-level access.

## Public URL Shape

The public base URL is the origin only:

```text
https://your-stable-or-temporary-host.example.com
```

The ChatGPT connector endpoint is:

```text
https://your-stable-or-temporary-host.example.com/mcp
```

Do not put `/mcp`, query tokens, fragments, or paths in
`DECISION_INBOX_PUBLIC_BASE_URL`.

## Stable Connector Run With OAuth Owner Password

Use this for repeated ChatGPT connector tests. This is the preferred path
because the ChatGPT connector URL stays clean:

```text
https://your-stable-host.example.com/mcp
```

The Owner password is entered only on the local server's OAuth approval page.
Do not put the Owner password or an access token in the connector URL.

1. Generate a fresh Owner password outside the repo:

   ```bash
   openssl rand -base64 32 > /tmp/decision-inbox-oauth-owner-token
   chmod 600 /tmp/decision-inbox-oauth-owner-token
   ```

2. Start the local server:

   ```bash
   DECISION_INBOX_PUBLIC_BASE_URL="https://your-stable-host.example.com" \
   python3 server/decision_inbox_http_server.py \
     --host 127.0.0.1 \
     --port 8765 \
     --oauth-owner-token-file /tmp/decision-inbox-oauth-owner-token
   ```

3. Point the tunnel or reverse proxy at:

   ```text
   http://127.0.0.1:8765
   ```

4. Configure ChatGPT with:

   ```text
   https://your-stable-host.example.com/mcp
   ```

5. Before asking ChatGPT to call tools, run preflight:

   ```bash
   DECISION_INBOX_PUBLIC_BASE_URL="https://your-stable-host.example.com" \
   python3 scripts/decision_inbox_preflight.py \
     --mode auto-mcp \
     --public-base-url "https://your-stable-host.example.com" \
     --require-public
   ```

   A pass means the local/public endpoints and OAuth challenge are reachable.
   If an OAuth state file or bearer token is available, the script also verifies
   the exact tool allowlist.

6. When ChatGPT opens the approval page, enter the Owner password from:

   ```text
   /tmp/decision-inbox-oauth-owner-token
   ```

7. After the test, stop the tunnel and server, delete the Owner password file,
   and scan the repo for accidental URL/token residue.

Risk coefficient while the tunnel is active: `3/5`. Risk returns to `1/5`
after the tunnel is stopped and temporary auth material is deleted.

## Optional Persistent OAuth State

Use this only when repeated ChatGPT connector runs should survive local server
restarts. Persistence is disabled unless `--oauth-state-file` or
`DECISION_INBOX_OAUTH_STATE_FILE` is explicitly set.

Persistent state stores OAuth client registrations plus access and refresh
tokens. Treat the state file as bearer-equivalent secret material. Authorization
codes are still one-time and are not persisted.

Recommended local-only storage path:

```bash
AUTH_DIR="$HOME/.local/share/decision-inbox-mcp-lab"
mkdir -p "$AUTH_DIR"
chmod 700 "$AUTH_DIR"

openssl rand -base64 32 > "$AUTH_DIR/oauth-owner-token"
chmod 600 "$AUTH_DIR/oauth-owner-token"

DECISION_INBOX_PUBLIC_BASE_URL="https://your-stable-host.example.com" \
python3 server/decision_inbox_http_server.py \
  --host 127.0.0.1 \
  --port 8765 \
  --oauth-owner-token-file "$AUTH_DIR/oauth-owner-token" \
  --oauth-state-file "$AUTH_DIR/oauth-state.json" \
  --oauth-refresh-token-ttl-seconds 604800
```

Risk coefficient:

- `2/5` when no public tunnel is active, because bearer-equivalent OAuth state
  exists on disk.
- `3/5` while the public tunnel is active with package-only tools and OAuth
  auth.
- `4/5` if the public tunnel is left running unattended for long periods, token
  files have loose permissions, or connector state becomes unclear.

To revoke the local persisted connector state:

```bash
python3 scripts/reset_decision_inbox_auth.py \
  --oauth-state-file "$AUTH_DIR/oauth-state.json" \
  --oauth-owner-token-file "$AUTH_DIR/oauth-owner-token"
```

After reset, ChatGPT may still show the account-side connector, but its stored
refresh token will no longer work against this local server state.

## Preflight

Run preflight before sending the prompt that asks ChatGPT to call MCP tools:

```bash
python3 scripts/decision_inbox_preflight.py \
  --mode auto-mcp \
  --public-base-url "https://your-stable-host.example.com" \
  --task-id "<task-id>" \
  --require-public
```

Expected Auto MCP result:

- local `/mcp` returns an auth challenge,
- public OAuth metadata is reachable,
- public `/mcp` returns an auth challenge for `decision-inbox`,
- authenticated `tools/list`, when a bearer token or non-expired OAuth access
  token is available, returns only:
  `list_decision_tasks`, `get_decision_package`, `submit_advice`, `get_task_status`.

If preflight fails, do not ask ChatGPT to use the connector yet. Fix the local
server, public URL, Funnel status, Host allowlist, or OAuth state first.

## Temporary Bearer-Token Tunnel Run

Use this for one-off tests only.

1. Start the local server with a temporary token:

   ```bash
   DECISION_INBOX_MCP_TOKEN="<temporary-token>" \
   DECISION_INBOX_PUBLIC_BASE_URL="https://temporary-host.example.com" \
   python3 server/decision_inbox_http_server.py --host 127.0.0.1 --port 8765
   ```

2. Point the tunnel at:

   ```text
   http://127.0.0.1:8765
   ```

3. Configure ChatGPT with:

   ```text
   https://temporary-host.example.com/mcp
   ```

4. Prefer Authorization bearer-token auth when the connector supports it. If a
   query-token URL is unavoidable, never screenshot or accessibility-read the
   connector form after the token is visible.

   Query-token URLs are not the stable recommended path. Use the OAuth Owner
   password flow above for ChatGPT connector runs whenever possible.

5. After the test, stop the tunnel and server, delete the token source, clear the
   clipboard if it held the URL, and scan the repo for accidental URL/token
   residue.

Risk coefficient while the tunnel is active: `3/5` with a token, `4/5` without a
token. Risk returns to `1/5` after the tunnel is stopped and token material is
deleted.

## Stable URL Run

Use this for repeated tests.

1. Put a stable HTTPS reverse proxy or tunnel in front of the local server.
2. Set:

   ```bash
   DECISION_INBOX_PUBLIC_BASE_URL="https://decision-inbox.example.com"
   ```

3. Keep the ChatGPT connector endpoint stable:

   ```text
   https://decision-inbox.example.com/mcp
   ```

This avoids the account-side problem where an already connected ChatGPT
development app may not expose a safe way to edit its MCP endpoint.

Risk coefficient: usually `2/5` to `3/5`, depending on the tunnel/provider
controls and whether OAuth Owner password approval is enabled.

## Read-Only Project Advisor Mode

Use Read-Only Project Advisor when the user wants ChatGPT Web to inspect
project content directly but not modify or execute anything. Select
GPT-5.5 Thinking for connector calls; do not use GPT-5.5 Pro for MCP/App tools.

Start:

```bash
DECISION_INBOX_PUBLIC_BASE_URL="https://your-stable-host.example.com" \
python3 server/decision_inbox_http_server.py \
  --mode read-only-project \
  --host 127.0.0.1 \
  --port 8765 \
  --allowed-root "$HOME/work/my-project"
```

Expected tools:

```text
open_workspace
ls
read
grep
glob
```

Do not generate a Decision Inbox package for this tier. ChatGPT reads the
allowed project content through the connector. High-risk credential paths such
as `.env*`, `.git`, SSH and cloud credential directories, private-key material,
and known token/OAuth state files are blocked. Other task-relevant project
files may be inspected by the advisor.

Risk coefficient: `3/5-4/5`.

## Full-Agent Mode

Use Full-Agent only when the user intentionally wants a DevSpace-like coding
connector. It exposes `open_workspace`, `read`, `write`, `edit`, `grep`, `glob`,
`ls`, and `bash` inside opened workspaces under configured allowed roots.

Full-Agent default auth files:

```text
~/.local/share/agent-decision-bridge/oauth-owner-token
~/.local/share/agent-decision-bridge/oauth-state.json
```

Recommended user-facing consultation wrapper:

```bash
python3 scripts/level3_consultation_flow.py prepare \
  --public-base-url "https://your-stable-host.example.com" \
  --allowed-root "$HOME/work/my-project" \
  --advisor-channel user-web \
  --advisor-health ready \
  "Review whether this project is ready for Level 3 use."
```

This wrapper checks the advisor gate, opens the short Full-Agent window, runs
public health checks, generates the compact ChatGPT Web prompt, and copies it to
the clipboard. It does not assume an advisor channel is ready by default; Codex
must explicitly pass `user-web`, `browser-automation`, or `direct-tool` with
`advisor-health=ready` before the `5/5` Full-Agent window opens. It closes the
window automatically if public health is not `stable`. Its defaults favor stable
Tailscale task windows over speed: 30 second public warmup, 30 second preflight
timeout, six open-time preflight attempts, and five public-health probes. If the
first health result is `intermittent`, the wrapper runs one extra full health
check before failing closed. A `failed` result still closes immediately.

Capture the returned ChatGPT Web answer as external advice data before local
review. This action refreshes the idle timer and leaves the window open by
default:

```bash
python3 scripts/level3_consultation_flow.py capture \
  --advisor chatgpt-web-full-agent \
  "<original Level 3 question>"
```

Use an explicit close only when you are stopping before advice has been captured
or the user wants to shut the high-risk window immediately:

```bash
python3 scripts/level3_consultation_flow.py close
```

The capture action stores the answer under
`decision-inbox/level3-consultations/` and renders a review-only gate. It does
not execute advisor instructions or change project files. By default, the
watchdog closes the session 20 minutes after the last Level 3 use. Each new
Level 3 action should call `touch` or go through the wrapper so the timer is
refreshed.

Low-level session window:

```bash
python3 scripts/full_agent_session.py open \
  --public-base-url "https://your-stable-host.example.com" \
  --allowed-root "$HOME/work/my-project" \
  --idle-timeout-seconds 1200
```

During an active Codex task, call `touch` after each Full-Agent consult step:

```bash
python3 scripts/full_agent_session.py touch
```

Inspect or close the window:

```bash
python3 scripts/full_agent_session.py status
python3 scripts/full_agent_session.py close
```

When the session is open, classify public endpoint stability with repeated
read-only preflight probes:

```bash
python3 scripts/full_agent_session.py status \
  --check-public-health \
  --health-attempts 3
```

Interpretation:

- `Public health: stable` means every preflight attempt passed.
- `Public health: intermittent` means at least one attempt passed and at least
  one failed. Treat the connector as usable for a short test, but not mature
  enough to call fully stable.
- `Public health: failed` means no public preflight passed. Do not ask ChatGPT
  Web to use the connector; fix Funnel/reverse proxy or switch provider.

The session helper starts the Full-Agent server, opens Tailscale Funnel unless
`--local-only` is set, runs read-only preflight, and starts a watchdog. The
watchdog closes the server and Funnel after the configured idle timeout.

Normal user-facing flow:

```text
User: Use Level 3 to consult ChatGPT about <question>.
Codex: prepares the consultation task, opens/touches the Full-Agent session,
checks whether an advisor channel is available, imports the advisor response,
and reports Adopt / Ask / Reject back to the user.
```

The user should not need to paste backend commands during normal product use.
Codex owns the session lifecycle for the current task window.

When debugging the prompt separately, generate the default product-review
prompt with:

```bash
python3 scripts/level3_consultation_prompt.py \
  --allowed-root "$PWD" \
  --clipboard \
  "Review whether this project is ready for Level 3 use."
```

This prompt asks ChatGPT Web to use only the connector, avoid Python/browser
file checks, start with read-only inspection, choose task-relevant files under
the allowed root, avoid high-risk credential paths, and report exactly what was
listed, searched, read, denied, or failed. Use `--deep` or explicit `--file`
arguments only when a targeted round needs a fixed file set. Earlier
2026-06-24 live runs used `docs/security-public.md` instead of raw
`docs/security.md` because the raw security file could trigger platform
tool-safety blocking.

Use `--clipboard` when Codex will hand the prompt to ChatGPT Web through
`user-web` or browser automation. It copies only the rendered prompt; it does
not open the public Full-Agent session and does not send anything by itself.

Important: Full-Agent is an inbound connector from ChatGPT Web into the local
workspace. It does not automatically give Codex an outbound GPT Pro call. If
Codex cannot see a `direct-tool` advisor channel and browser automation is not
authorized, the correct state is `waiting_for_advisor_channel`; the product must
ask the user to trigger ChatGPT Web manually or authorize browser automation.
For connector calls, ChatGPT Web should use GPT-5.5 Thinking rather than
GPT-5.5 Pro. OpenAI's current ChatGPT docs state that Pro models do not expose
Apps/MCP tools.

Browser automation note: ChatGPT Web is a heavy frontend. Avoid using full DOM
snapshots as the primary automation path; they have timed out in this lab. Keep
prompts compact, prefer a visible prompt box / clipboard paste path, and verify
success through both the ChatGPT answer and the local MCP server log. If browser
automation cannot enter text reliably, close the `5/5` session and fall back to
`user-web` instead of leaving Full-Agent exposed.

Start:

```bash
DECISION_INBOX_PUBLIC_BASE_URL="https://your-stable-host.example.com" \
python3 server/decision_inbox_http_server.py \
  --mode full-agent \
  --host 127.0.0.1 \
  --port 8765 \
  --allowed-root "$HOME/work/my-project"
```

Disable OAuth persistence only when needed:

```bash
python3 server/decision_inbox_http_server.py \
  --mode full-agent \
  --host 127.0.0.1 \
  --port 8765 \
  --allowed-root "$HOME/work/my-project" \
  --oauth-state-file none
```

Doctor:

```bash
python3 scripts/decision_inbox_doctor.py --mode full-agent
```

Revoke default Full-Agent auth files:

```bash
python3 scripts/reset_decision_inbox_auth.py --full-agent-defaults
```

Risk coefficient: `5/5`. Bash runs with the local user account and is not a
sandbox. Do not use broad roots such as home or filesystem root. The idle
timeout reduces exposure time only; it does not reduce the risk while the
session is open.

## Stable URL Without Owned Domain: Tailscale Funnel

Use Tailscale Funnel when the user does not own a domain but wants a stable
public HTTPS URL.

Verified public origin for this lab:

```text
https://your-device.example-tailnet.ts.net
```

Verified public MCP endpoint:

```text
https://your-device.example-tailnet.ts.net/mcp
```

This run used a project-scoped userspace daemon instead of the macOS system
extension app:

```bash
tailscaled \
  --tun=userspace-networking \
  --socket=/tmp/tailscaled-decision-inbox.sock \
  --statedir="$HOME/.local/share/tailscale-decision-inbox"
```

After browser login, start the local MCP server with OAuth Owner password auth:

```bash
openssl rand -base64 32 > /tmp/decision-inbox-oauth-owner-token
chmod 600 /tmp/decision-inbox-oauth-owner-token

export DECISION_INBOX_PUBLIC_BASE_URL="https://your-device.example-tailnet.ts.net"

python3 server/decision_inbox_http_server.py \
  --host 127.0.0.1 \
  --port 8765 \
  --oauth-owner-token-file /tmp/decision-inbox-oauth-owner-token
```

Enable Funnel:

```bash
tailscale --socket=/tmp/tailscaled-decision-inbox.sock funnel --bg --yes 8765
```

Check status:

```bash
tailscale --socket=/tmp/tailscaled-decision-inbox.sock funnel status
python3 scripts/decision_inbox_doctor.py
python3 scripts/decision_inbox_preflight.py \
  --mode auto-mcp \
  --public-base-url "https://your-device.example-tailnet.ts.net" \
  --require-public
```

### Local Preflight Stability Notes

When testing a Tailscale Funnel endpoint from the same Mac that owns the
userspace daemon, local DNS and TLS can be less stable than the remote ChatGPT
side:

- run Tailscale CLI commands with `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY`
  removed,
- flush macOS DNS cache before strict public preflight if `.ts.net` recently
  returned a negative lookup,
- allow a 10 second warmup after `tailscale funnel --bg --yes <port>` before
  public preflight,
- use the preflight script's curl fallback for unauthenticated public metadata
  and challenge checks when Python's urllib hits intermittent SSL EOF errors.

2026-06-24 Tailscale note: local public preflight against
`your-device.example-tailnet.ts.net` reproduced intermittent `LibreSSL
SSL_connect: SSL_ERROR_SYSCALL` and timeout failures on the first two attempts,
then passed on the third attempt with a longer warmup and 10 second request
timeout. Treat one early public preflight failure as a warmup signal, not as an
immediate reason to switch providers. Switch to Cloudflare only if repeated
warmup/retry runs fail or if ChatGPT Web cannot reach the connector while the
local server and authenticated tool probe are healthy.

Later 2026-06-24 retest: two immediate preflights passed and one follow-up
public challenge probe timed out while authenticated `tools/list` still passed.
Classify that state as `Public health: intermittent`, not as fully stable. The
local Tailscale daemon also reported macOS Screen Time may be blocking
Tailscale; that system setting is a plausible source of repeated Funnel
instability.

Latest 2026-06-24 retest: with a 15 second public warmup, 15 second preflight
timeout, and repeated health checks, `status --check-public-health` passed 5/5
and ChatGPT Web completed a real Full-Agent connector read of the default three
files. Classify this as conditionally usable for a bounded Level 3 task window
after a passing health check. Do not classify it as an always-on stable public
URL while the macOS Screen Time Tailscale health warning remains.

Follow-up 2026-06-24 Tailscale retest: using the conservative Level 3 defaults
of 30 second public warmup, 30 second preflight timeout, six open-time preflight
attempts, and five status health probes, open-time preflight passed, direct
public OAuth metadata returned HTTP 200, direct public `/mcp` returned the
expected HTTP 401 OAuth challenge, and `status --check-public-health` passed
5/5. After closing, `funnel status` returned `No serve config` and port 8765 was
not listening. Treat Tailscale as usable for short verified windows; use
Cloudflare Named Tunnel only for a more production-like stable endpoint or if
these health checks regress.

Disable Funnel:

```bash
tailscale --socket=/tmp/tailscaled-decision-inbox.sock funnel reset
```

Risk coefficient while Funnel is active: `3/5`.

Lifecycle helper:

```bash
python3 scripts/decision_inbox_tunnel_window.py open \
  --mode auto-mcp \
  --public-base-url "https://your-device.example-tailnet.ts.net" \
  --task-id "<task-id>"

python3 scripts/decision_inbox_tunnel_window.py status

python3 scripts/decision_inbox_tunnel_window.py close
```

The helper opens Tailscale Funnel, runs preflight, and prints the active risk
coefficient. It does not create or edit the ChatGPT account-side connector.

Do not leave Funnel on after the connector test. In the 2026-06-21 verification,
public scanner traffic hit common paths such as `/.env`, `/.git/config`, and
`/server-status` within minutes. The server rejected them, but the endpoint
should be treated as actively exposed whenever Funnel is on.

## Local Doctor

Run:

```bash
python3 scripts/decision_inbox_doctor.py
```

With a public URL:

```bash
DECISION_INBOX_PUBLIC_BASE_URL="https://decision-inbox.example.com" \
DECISION_INBOX_OAUTH_OWNER_TOKEN="<owner-password>" \
python3 scripts/decision_inbox_doctor.py
```

The doctor prints:

- local MCP URL,
- public MCP URL,
- bearer-token and Owner-password presence and length, never secret values,
- local probe status,
- risk coefficient,
- connector lifecycle warning.
- preflight command suggestion.

## Host Allowlist

The HTTP server now accepts only these Host headers by default:

- `localhost`,
- `127.0.0.1`,
- `::1`,
- the bind host,
- the hostname from `DECISION_INBOX_PUBLIC_BASE_URL`.

Add an intentional host only when needed:

```bash
python3 server/decision_inbox_http_server.py --allow-host decision-inbox.example.com
```

Do not use a broad Host allowlist for web-advisor testing unless it is a local
debug session with no public tunnel.

## Connector Lifecycle Reality

Changing `DECISION_INBOX_PUBLIC_BASE_URL` updates the local server metadata and
Host allowlist. It does not automatically update a ChatGPT account-side
connector that is already connected to an older endpoint.

If the public URL changes, the safe choices are:

- use a stable URL so the connector does not need endpoint edits,
- reconnect or recreate the ChatGPT development app deliberately,
- fall back to manual Decision Inbox package paste for one-off consultation.
