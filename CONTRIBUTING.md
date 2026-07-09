# Contributing

Thanks for helping improve Agent Decision Bridge.

## Development Rules

- Keep the public product language focused on Ask First and Connected Agent.
- Treat legacy connector names as compatibility details, not user-facing
  product copy.
- Do not commit secrets, tunnel tokens, OAuth state, local credentials, browser
  data, generated marketing assets, or private project files.
- Keep examples synthetic and safe to share.
- Update docs when workflow, permissions, tool surfaces, or safety boundaries
  change.
- Add or update tests for server behavior, connector permissions, session
  lifecycle, and helper output.

## Verification

Run the full test suite before opening a PR:

```bash
python3 -m unittest discover -s tests
```

For Connected Agent changes, also run the relevant doctor or preflight command
against a local test setup before asking ChatGPT Web to use a connector.

## Pull Request Checklist

- The README still presents a clean two-mode product model.
- Public docs do not suggest sharing one maintainer-owned endpoint across users.
- Connected Agent still requires an allowed root.
- Secret paths and out-of-root paths remain blocked.
- Side-effectful actions remain approval-gated unless the documented hidden
  session switch is explicitly enabled.
