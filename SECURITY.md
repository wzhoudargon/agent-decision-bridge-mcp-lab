# Security Policy

Agent Decision Bridge is self-hosted software. Users control their own local
server, public HTTPS endpoint, OAuth state, and allowed project roots.

## Supported Boundary

- Ask First has no public MCP exposure.
- Connected Agent requires an explicit allowed root and a short authenticated
  project window.
- External advisor output is advice, not authorization.
- The current user remains the only authority for file edits, shell commands,
  dependency installs, Git operations, publishing, deletion, and use of secrets.
- Public endpoints must be user-provided. Do not route multiple users through a
  shared maintainer-owned tunnel or domain.

## Sensitive Data

Do not store or report:

- API keys, access tokens, private keys, passwords, or OAuth state files,
- `.env*`, `.git`, SSH/cloud credential directories, browser data, or cookies,
- customer data, private emails, or proprietary documents.

## Reporting Issues

Open a GitHub issue for security-relevant behavior without including sensitive
data. If the report requires private details, first open a minimal issue asking
for a private disclosure channel.
