# RedSkill Upload Notes

Use this local Skill directory for Xiaohongshu SkillHub upload:

```text
redskill-upload/agent-decision-bridge
```

Do not upload the whole GitHub repository. Do not upload a manually zipped file.
Pass the local Skill directory to the RedSkill upload CLI and let the CLI bundle
it.

Run commands from the repository root. Set `SKILLHUB_CLI` to your local
RedSkill upload CLI entrypoint if it is not already on `PATH`.

## Dry Run Result

Validated with:

```bash
"${SKILLHUB_CLI:-skillhub-upload}" \
  publish redskill-upload/agent-decision-bridge \
  --dry-run \
  --agent \
  --source original \
  --tag 效率工具 \
  --identifier agent-decision-bridge
```

Expected payload:

```text
status: dry_run
name: codex外接最强助理
skill_identifier: agent-decision-bridge
version: 1.0.0
description: 把 ChatGPT 网页端变成 Codex 的外部 Agent：Pro 做深度咨询，Thinking 接 MCP 工具，Codex 保留本地验证和执行。
source: original / 原创
tag: 效率工具
content_tag_ids: 1001
bundle_size_bytes: 10099
```

Important: keep `--identifier agent-decision-bridge`. Without it, the current
CLI derives `codex` from the Chinese display name, which is not the intended
stable Skill ID.

## Upload Command

If not logged in:

```bash
"${SKILLHUB_CLI:-skillhub-upload}" login --agent
```

Submit after login:

```bash
printf 'submit\n' | "${SKILLHUB_CLI:-skillhub-upload}" \
  publish redskill-upload/agent-decision-bridge \
  --agent \
  --source original \
  --tag 效率工具 \
  --identifier agent-decision-bridge
```

Use `cancel` instead of `submit` if you want to test the CLI confirmation path
without uploading:

```bash
printf 'cancel\n' | "${SKILLHUB_CLI:-skillhub-upload}" \
  publish redskill-upload/agent-decision-bridge \
  --agent \
  --source original \
  --tag 效率工具 \
  --identifier agent-decision-bridge
```
