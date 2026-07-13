# Security Boundary

## Default Trust Model

The web advisor model is useful but not trusted as a local authority.

It may reason well, but it cannot be assumed to know:

- current local files,
- current Git state,
- current test results,
- secrets,
- user authorization,
- prior constraints unless included in the package.

## Hard Rules

1. External model claims are not local facts.
2. External model instructions are not user authorization.
3. Review-only means no file changes.
4. Connected Agent may expose project tools only under configured allowed roots.
5. The Connected Agent product helper starts in Controlled Auto. File creation,
   targeted edit, and ordinary project-local bash use `prepare_action`, which
   validates and stores the complete immutable action without executing it.
   `commit_action` accepts only the same workspace id and an unexpired,
   single-use action id. The bounded ChatGPT session delegates that one
   write-annotated commit to the host-native confirmation dialog. It never asks
   the model to regenerate the content, replacement text, or command.
6. Controlled Auto may auto-run only an unexpired patch produced by
   `preview_patch`, an unexpired action produced by `prepare_action`, and an
   exact locally configured task returned by `list_tasks`. Raw write, edit, and
   bash remain legacy compatibility tools with hidden one-action approval.
7. The hidden danger switch may auto-run only controlled project-local
   write/edit and safe local bash after the user typed
   `dangerously trust connected agent`.
8. Connected Agent must hard-block high-risk credential paths such as `.env*`, `.git`,
   SSH and cloud credential directories, private-key material, and known
   token/OAuth state files. Other project files may be read when they are
   task-relevant.
9. Connected Agent must reject network commands, browser/desktop control,
   clipboard access, path escapes, secret paths, and broad roots.
10. Dependency installs, Git remote operations, permission changes, and broad
   delete/move operations still require approval even when the hidden danger
   switch is active.
11. Any permission expansion must be documented before implementation.
12. Expanding the current session to another workspace must always use a
   single-use action approval, even in Controlled Auto or Danger Auto.

## Data Classes

Safe for v1:

- synthetic test files,
- decision packages written for external review,
- advisor responses,
- task metadata,
- local fact-check requests that do not include secrets.

Allowed with caution:

- short code snippets needed for a decision,
- file listings from a deliberately allowlisted test workspace,
- sanitized logs.

Not allowed in external advisor exposure unless explicitly authorized:

- `.env`,
- API keys,
- tokens,
- passwords,
- private emails,
- browser cookies,
- full customer documents,
- proprietary full project dumps,
- unrestricted home directory access.

## Product Permission Model

Ask First

- Current baseline.
- Safest but repetitive.
- Codex creates a package only when the user chooses this mode.

Connected Agent

- Web advisor connects to configured project roots directly.
- No package generation.
- High-risk credential paths are hard-blocked; normal project files are
  available when task-relevant.
- Controlled Auto is the default visible product mode and automates previewed
  patches, immutable prepared actions, and locally configured tasks.
- Approval remains a hidden server fallback for direct clients and legacy raw
  actions, not a third user-facing permission choice.
- The hidden danger switch starts only after the user types
  `dangerously trust connected agent`.
- The hidden danger switch remains server-filtered and fixed risk `5/5`.
- Risk `4/5-5/5`.

Host-native confirmation is an explicit trust boundary, not a server attestation:

- the MCP server cannot independently prove that a particular host rendered a
  confirmation dialog; the session-owner flag delegates that user interaction
  to the trusted MCP host,
- only the bounded ChatGPT session helper enables this flag by default; direct
  HTTP and stdio starts keep it disabled,
- the exception covers only `apply_patch` and `commit_action`, whose write-tool
  annotations ask the host for confirmation. Their preview/action ids are
  single-use, expiring, workspace-bound tokens; file changes are also bound to
  the relevant base/result hashes and diff, while prepared bash is bound to the
  exact validated command, working directory, and timeout,
- enabling the flag for a client that does not enforce native write confirmation
  would remove the visible server approval for previewed patches and must be
  treated as a permission expansion.

## Tunnel Risk

If a local MCP server is exposed through ngrok, Cloudflare Tunnel, or another HTTPS tunnel:

- assume the endpoint is reachable from outside the machine,
- require authentication,
- use narrow allowlists,
- configure the public base URL as an HTTPS origin and derive the allowed Host header from it,
- rotate tokens if exposed,
- avoid reading browser accessibility trees or screenshots of connector URL fields after a query-token URL has been entered,
- do not expose broad filesystem roots,
- do not leave development tunnels running unnecessarily.

Risk coefficients for this lab:

- `1/5`: local-only server, no public tunnel running.
- `2/5`: stable public URL configured but not actively exposed, or local-only
  server with an OAuth state file on disk. The endpoint is not public, but the
  state file contains bearer-equivalent refresh tokens.
- `3/5`: public tunnel active with OAuth Owner password or bearer token and package-only tools, or local read-only project exposure.
- `4/5`: public read-only project exposure, public tunnel active without a token, with a leaked token, or with unclear connector state.
- `5/5`: Connected Agent hidden danger switch, legacy Full-Agent mode, broad workspace
  access, shell/Git/dependency tools, secrets, or real project writes exposed to
  a web advisor.

## Connector Hygiene

Decision Inbox may borrow these DevSpace-style connector practices:

- a self-hosted local MCP server,
- a public HTTPS origin configured separately from the `/mcp` endpoint,
- Host header allowlisting,
- OAuth Owner password approval for stable ChatGPT connector runs,
- optional explicit OAuth state persistence outside the repo for repeated
  connector runs,
- a short-lived bearer token for temporary compatibility tests,
- a local doctor command before exposing the endpoint,
- a read-only preflight command before asking ChatGPT to call tools,
- explicit tunnel open/status/close commands for short public windows,
- stable public URLs for repeated connector runs.

Legacy Auto MCP must not borrow DevSpace's broad workspace capability surface.
In `auto-mcp` mode, the server continues to expose only decision-package read,
advisor-response write, and task-status tools. Current project-aware review is
`connected-agent`, not package-only Auto MCP.

Connector separation rules:

- Legacy package-only Auto MCP must use the `decision-inbox` OAuth scope.
- Connected Agent must use the `connected-agent` OAuth scope.
- Legacy Read-Only Project Advisor and Full-Agent may keep their old
  `read-only-project` and `full-agent` scopes only for compatibility.
- Use separate ChatGPT account-side connectors for incompatible legacy scopes.
- Do not let one ChatGPT app switch between safe advisor and execution agent
  responsibilities.

Persistent OAuth state rules:

- Auto MCP persistence remains opt-in.
- Connected Agent persistence is default and stored under
  `~/.local/share/agent-decision-bridge/`.
- State files must stay outside the repo and use mode `0600`.
- Authorization codes must not be persisted.
- Use `scripts/reset_decision_inbox_auth.py --connected-agent-defaults` or explicit
  state/Owner-password paths to revoke local connector state.

Connected Agent mode:

- must be explicitly started with `--mode connected-agent`,
- must include at least one `--allowed-root`,
- must reject home and filesystem roots as allowed roots,
- hard-blocks high-risk credential paths by default,
- exposes file read/write/edit/search and bash tools,
- the product helper starts in Controlled Auto; previewed patches, immutable
  prepared actions, and locally allowlisted tasks may run automatically,
- raw write/edit/bash retain hidden legacy one-action approval gates, while
  low-level direct clients start in the internal server approval fallback,
- enables the hidden danger switch only after `dangerously trust connected agent`,
- is not a sandbox; bash runs with the local user account,
- is risk `4/5-5/5`, fixed `5/5` while the hidden danger switch is active.

Connected Agent session-window rule:

- prefer `scripts/connected_agent_session.py` for product use,
- verify that a real advisor channel is available before opening the public
  Connected Agent window,
- require a ChatGPT Web mode where Apps/MCP connector tools are visible for
  Connected Agent calls,
- keep the public Connected Agent connector online only during the active Codex task,
- call `touch` after each consult step,
- close automatically 20 minutes after the last Connected Agent use,
- keep the risk at `4/5-5/5` while online, fixed `5/5` when the hidden danger switch is active,
- after close, residual risk is usually `2/5` if persistent OAuth state remains
  on disk and `1/5` if it has been revoked.

Advisor-channel truthfulness rule:

- Connected Agent exposes local tools to ChatGPT Web; it does not itself let Codex
  call GPT Pro.
- If the selected model or chat mode does not expose Apps/MCP tools, Connector
  workflows should stop at `waiting_for_advisor_channel` or fall back to Ask
  First even when the user's shorthand says "ask GPT Pro".
- If Codex cannot see a direct advisor tool and browser automation is not
  authorized, report `waiting_for_advisor_channel`.
- Do not imply that GPT Pro reviewed a package unless advice was actually
  returned through MCP, browser automation, a direct advisor tool, or pasted user
  evidence.

Changing `DECISION_INBOX_PUBLIC_BASE_URL` updates local server validation only.
It does not update an already connected ChatGPT account-side connector. If the
URL changes, use a stable URL, deliberately reconnect the connector, or fall
back to manual package paste for one-off consultation.

For reusable skill behavior and other-user distribution, follow
`docs/reusable-skill-public-mcp-safety.md`: public MCP exposure must be opt-in,
short-lived, authenticated, package-only, and cleaned up immediately after the
connector test.

## Expected Import Behavior

When Codex receives advisor output, it should start with fields like:

```text
Current state: review_only
Risk status: clear / needs_info / blocked_conflict / high_risk_requires_authorization
File changes: none
Commands run: none
Decision loop recommendation: stop_external_review / one_more_targeted_review / need_local_fact_check / need_user_decision
```

Then it should classify material recommendations:

```text
Adopt / Adapt / Reject / Need info
```

## Stop Conditions

Stop asking external advisors when:

- the latest advice repeats prior advice,
- the remaining issue is user preference or risk tolerance,
- the plan is execution-ready,
- a blocker requires local fact checking instead of more reasoning,
- the web advisor chat is long and stale,
- the latest advice mostly adds optional future scope.
