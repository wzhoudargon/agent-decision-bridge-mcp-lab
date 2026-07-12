# Agent Decision Bridge

Agent Decision Bridge is a self-hosted MCP workflow that lets Codex work with
ChatGPT Web as an external advisor while Codex keeps local verification and
execution control.

It is designed for users who want a stronger second opinion on project
architecture, product plans, content outlines, or code changes without turning a
web model into unchecked local authority.

## Modes

| Mode | Best for | Connector exposure | Default risk |
|---|---|---:|---:|
| Ask First | Deep manual review with GPT Pro, Claude, Gemini, or another advisor | None | `1/5` |
| Connected Agent | Letting ChatGPT Web inspect an allowed project root through MCP | Short-lived authenticated project window | `3/5-5/5` |

Ask First produces a focused review package for manual advisor review.
Connected Agent opens a bounded project window so ChatGPT Web can list, search,
and read task-relevant files inside an allowed root. Write, edit, and shell
requests use one-action approval by default.

External advice is never authorization. Codex remains the local fact checker and
executor, and the current user remains the only authority for side effects.

## Requirements

- Python `>=3.9`
- No third-party Python packages for the core scripts or tests
- ChatGPT Web with connector-capable Apps/MCP tools for Connected Agent
- A user-provided public HTTPS endpoint for Connected Agent, such as Tailscale
  Funnel, Cloudflare Tunnel, ngrok, Pinggy, or a self-managed HTTPS reverse
  proxy

Ask First does not require a public endpoint.

## Quick Start

Run the test suite:

```bash
python3 -m unittest discover -s tests
```

Prepare an Ask First review package:

```bash
python3 scripts/prepare_consultation.py \
  --mode ask-first \
  --advisor-channel manual \
  "Review whether this project architecture is ready to ship."
```

Prepare a Connected Agent consultation:

```bash
python3 scripts/connected_agent_flow.py prepare \
  --allowed-root "$PWD" \
  --public-base-url "https://your-public-host.example.com" \
  --advisor-channel user-web \
  --advisor-health ready \
  "Review whether this project structure should be simplified."
```

After ChatGPT Web returns advice, capture it as review data:

```bash
python3 scripts/connected_agent_flow.py capture \
  --advisor chatgpt-web-connected-agent \
  "Review whether this project structure should be simplified."
```

Close the session explicitly when needed:

```bash
python3 scripts/connected_agent_flow.py close
```

## Connected Agent Flow

Connected Agent is an inbound connector:

```text
ChatGPT Web -> MCP connector -> local Agent Decision Bridge tools
```

The normal flow is:

1. Codex verifies the advisor channel and allowed project root.
2. Codex opens a short Connected Agent session.
3. ChatGPT Web uses the connector to inspect task-relevant files.
4. ChatGPT Web returns advice.
5. Codex captures the advice as data.
6. Codex classifies recommendations as `Adopt`, `Adapt`, `Reject`, or
   `Need info`.
7. The session is closed manually or by idle timeout.

Connected Agent does not automatically give Codex an outbound GPT Pro call. If
Codex cannot reach a real advisor channel, the correct state is
`waiting_for_advisor_channel`.

## Security Model

Agent Decision Bridge is built around explicit boundaries:

- allowed project roots are required for Connected Agent,
- home and filesystem roots are rejected,
- `.env*`, `.git`, SSH/cloud credentials, private-key material, and known token
  or OAuth state files are blocked,
- writes, edits, and shell commands require one-action approval by default,
- dependency installation, Git remote operations, broad destructive actions,
  browser/desktop control, clipboard access, network commands, and path escapes
  are denied or approval-gated,
- public endpoints are bring-your-own and should be short-lived,
- one shared maintainer-owned public tunnel must not be used for other users.

See [docs/security-public.md](docs/security-public.md) for the concise public
safety summary and [docs/security.md](docs/security.md) for implementation
details.

## Repository Layout

```text
.
├── decision-inbox/        # File-based package/advice exchange for Ask First and legacy compatibility
├── docs/                  # User guide, architecture, runbooks, and verification notes
├── scripts/               # Consultation, session, preflight, capture, reset, and import helpers
├── server/                # MCP stdio and Streamable HTTP server implementations
├── test-workspace/        # Synthetic workspace used for restricted-access tests
└── tests/                 # Python unittest coverage
```

The main entry documents are:

- [docs/user-guide.md](docs/user-guide.md)
- [docs/connected-agent-user-flow.md](docs/connected-agent-user-flow.md)
- [docs/connector-runbook.md](docs/connector-runbook.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/update-notes.md](docs/update-notes.md)

## Development

Run all tests:

```bash
python3 -m unittest discover -s tests
```

Run connector preflight before asking ChatGPT Web to use a public endpoint:

```bash
python3 scripts/decision_inbox_preflight.py \
  --mode connected-agent \
  --public-base-url "https://your-public-host.example.com" \
  --require-public
```

Check local connector status:

```bash
python3 scripts/decision_inbox_doctor.py --mode connected-agent
```

Reset local connector auth state:

```bash
python3 scripts/reset_decision_inbox_auth.py --connected-agent-defaults
```

## Status

Agent Decision Bridge is under active productization. The current public model
is Ask First plus Connected Agent. Older compatibility paths remain covered by
tests, but new user-facing documentation should use the two-mode language above.

## License

No open-source license has been selected yet. Add a `LICENSE` file before
publishing redistribution terms.
