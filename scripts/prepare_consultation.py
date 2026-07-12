#!/usr/bin/env python3
"""Prepare a Decision Inbox consultation task from a conversational request."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS_ROOT = ROOT / "decision-inbox" / "tasks"
TASK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_RE = re.compile(r"[^a-z0-9]+")
ZH_RE = re.compile(r"[\u3400-\u9fff]")
VALID_MODES = {"ask-first", "connected-agent", "auto-mcp", "read-only-project", "full-agent"}
PACKAGE_MODES = {"ask-first", "auto-mcp"}
LANGUAGES = {"auto", "en", "zh"}
NOT_CONSULTED_NOTICE = (
    "The target advisor has not been consulted yet; the package is ready and waiting to be sent."
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a conversation-first Decision Inbox consultation package."
    )
    parser.add_argument("question", help="User consultation request.")
    parser.add_argument(
        "--mode",
        choices=sorted(PACKAGE_MODES),
        default="ask-first",
        help="Package mode. Defaults to Ask First; Auto MCP is legacy compatibility.",
    )
    parser.add_argument("--title", default=None)
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--advisor", default="chatgpt-pro")
    parser.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT)
    parser.add_argument(
        "--advisor-channel",
        choices=["unknown", "manual", "user-web", "browser-automation", "direct-tool"],
        default=None,
        help="How Codex can reach the external advisor in the current environment.",
    )
    parser.add_argument(
        "--language",
        choices=sorted(LANGUAGES),
        default="auto",
        help="Package language. Auto selects Chinese when the title or question contains Chinese.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    advisor_channel = args.advisor_channel or (
        "manual" if args.mode == "ask-first" else "unknown"
    )
    try:
        result = create_consultation_task(
            tasks_root=args.tasks_root,
            question=args.question,
            mode=args.mode,
            title=args.title,
            task_id=args.task_id,
            advisor=args.advisor,
            advisor_channel=advisor_channel,
            language=args.language,
        )
    except Exception as exc:
        print(f"prepare_consultation: {exc}", file=sys.stderr)
        return 1
    print(render_status(result))
    return 0


def create_consultation_task(
    tasks_root: Path,
    question: str,
    mode: str,
    title: Optional[str] = None,
    task_id: Optional[str] = None,
    advisor: str = "chatgpt-pro",
    allowed_roots: Optional[List[str]] = None,
    advisor_channel: str = "unknown",
    language: str = "auto",
) -> Dict[str, Any]:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(VALID_MODES))}")
    if mode not in PACKAGE_MODES:
        raise ValueError(
            f"{mode} does not create a decision package. Use direct workspace MCP tools instead."
        )
    if not question.strip():
        raise ValueError("question must be non-empty")
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of: {', '.join(sorted(LANGUAGES))}")
    tasks_root.mkdir(parents=True, exist_ok=True)
    task_title = title or title_from_question(question)
    resolved_language = resolve_language(language, task_title, question)
    resolved_task_id = task_id or unique_task_id(tasks_root, task_title)
    validate_task_id(resolved_task_id)
    task_dir = tasks_root / resolved_task_id
    if task_dir.exists():
        raise FileExistsError(f"Task already exists: {resolved_task_id}")
    task_dir.mkdir()
    (task_dir / "advice").mkdir()
    (task_dir / "fact-check-requests").mkdir()

    now = utc_timestamp()
    normalized_allowed_roots = [str(Path(item).expanduser()) for item in (allowed_roots or [])]
    metadata = {
        "task_id": resolved_task_id,
        "title": task_title,
        "status": "package_ready",
        "created_at": now,
        "updated_at": now,
        "created_by": "codex",
        "advisor_rounds": 0,
        "product_mode": mode,
        "advisor": advisor,
        "advisor_channel": advisor_channel,
        "language": resolved_language,
        "risk_level": risk_level(mode),
        "allowed_roots": normalized_allowed_roots,
        "allowed_inputs": ["metadata.json", "package.md", "advice/*.md"],
        "disallowed_inputs": disallowed_inputs(mode),
        "next_local_action": next_local_action(mode, advisor_channel, resolved_task_id),
    }
    (task_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
    )
    (task_dir / "package.md").write_text(
        render_package(
            title=task_title,
            question=question,
            mode=mode,
            advisor=advisor,
            advisor_channel=advisor_channel,
            language=resolved_language,
        ),
        encoding="utf-8",
    )
    return {
        "task_id": resolved_task_id,
        "task_dir": task_dir,
        "package_path": task_dir / "package.md",
        "metadata_path": task_dir / "metadata.json",
        "mode": mode,
        "advisor": advisor,
        "advisor_channel": advisor_channel,
        "language": resolved_language,
        "risk_level": metadata["risk_level"],
        "next_local_action": metadata["next_local_action"],
    }


def render_package(
    title: str,
    question: str,
    mode: str,
    advisor: str,
    advisor_channel: str,
    language: str,
) -> str:
    if language == "zh":
        return render_package_zh(
            title=title,
            question=question,
            mode=mode,
            advisor=advisor,
            advisor_channel=advisor_channel,
        )
    return render_package_en(
        title=title,
        question=question,
        mode=mode,
        advisor=advisor,
        advisor_channel=advisor_channel,
    )


def render_package_en(
    title: str,
    question: str,
    mode: str,
    advisor: str,
    advisor_channel: str,
) -> str:
    return f"""# {title}

## Instructions For The External Advisor

You are an external advisor. Use only the facts in this package. Do not assume
access to local files, screenshots, code, logs, Git state, shell commands,
browser data, or previous chat history that is not provided here.

External advice only. This is not authorization.

## Product Mode

- Requested mode: {mode}
- Target advisor: {advisor}
- Advisor channel visible to Codex now: {advisor_channel}
- A prepared package does not mean the advisor has already been consulted.

## Goal

{question.strip()}

## Current Facts

- Codex is the local fact checker and executor.
- External model output is advice, not authorization.
- No additional project-specific facts were supplied to this helper. State any
  missing fact that materially limits the recommendation.

## Assumptions

- Do not invent local file contents, test results, Git state, permissions, or
  prior decisions.

## Settled Decisions

- Ask First creates a package and does not open Connected Agent.
- Material recommendations return to Codex for local review before execution.

## Constraints

- Do not request secrets, credentials, browser data, full private dumps, or broad
  filesystem access.
- Do not ask Auto MCP to run shell, inspect Git, install dependencies, or edit files.
- Do not merge Ask First package flow and Connected Agent workspace flow.

## Please Output

1. Recommended approach
2. Why this approach
3. Classify material recommendations as Adopt / Adapt / Reject / Need info
4. Missing information, if any
5. Concrete next steps for Codex
6. Verification or acceptance criteria
7. Main risks

When writing advice back through MCP, include the exact marker:

```text
External advice only. This is not authorization.
```
"""


def render_package_zh(
    title: str,
    question: str,
    mode: str,
    advisor: str,
    advisor_channel: str,
) -> str:
    return f"""# {title}

## 给外部模型的说明

你是外部顾问型 AI。请只基于本包提供的信息判断，不要假设你能访问未提供的本地文件、截图、代码、日志、Git 状态、浏览器数据或历史对话。

外部建议只用于评审，不构成执行授权。

## 产品模式

- 请求模式：{mode}
- 目标顾问：{advisor}
- 当前 advisor channel：{advisor_channel}
- 决策包已准备好，不等于顾问已经被实际咨询。

## 目标

{question.strip()}

## 当前事实

- Codex 是本地事实核查者和执行者。
- 外部模型输出是建议，不是授权。
- helper 未收到更多项目专属事实；如果缺失事实会实质影响结论，请明确指出。

## 推测与假设

- 不要虚构本地文件内容、测试结果、Git 状态、权限或既往决策。

## 已定决策

- Ask First 只创建决策包，不开启 Connected Agent。
- 重要建议必须返回 Codex 做本地核查后，才可能进入执行授权。

## 约束与隐私边界

- 不要请求密钥、凭据、浏览器数据、完整私密资料或宽泛文件系统权限。
- 不要要求 Auto MCP 执行 shell、检查 Git、安装依赖或编辑文件。
- 不要混合 Ask First 决策包流程与 Connected Agent 工作区流程。

## 请输出

1. 推荐方案
2. 理由
3. 将重要建议分类为 Adopt / Adapt / Reject / Need info
4. 缺失信息（如有）
5. 给 Codex 的具体下一步
6. 验收标准
7. 主要风险

结尾必须保留：

```text
External advice only. This is not authorization.
```
"""


def render_status(result: Dict[str, Any]) -> str:
    task_id = result["task_id"]
    mode = result["mode"]
    lines = [
        "Current state: consultation_package_ready",
        f"Mode: {mode}",
        f"Risk coefficient: {result['risk_level']}",
        f"Advisor channel: {result['advisor_channel']}",
        f"Language: {result['language']}",
        f"Task id: {task_id}",
        f"Package: {result['package_path']}",
        f"Next local action: {result['next_local_action']}",
        NOT_CONSULTED_NOTICE,
    ]
    if result["advisor_channel"] in {"unknown", "manual", "user-web"}:
        lines.extend(
            [
                "",
                "Manual handoff:",
                advisor_prompt(mode, task_id, result["advisor"]),
            ]
        )
    return "\n".join(lines)


def advisor_prompt(mode: str, task_id: str, advisor: str) -> str:
    if mode == "auto-mcp":
        return (
            f"Use the Auto MCP Controlled Advisor connector. Call get_decision_package "
            f"for task_id={task_id}, answer only from that package, then call "
            f"submit_advice with advisor={advisor}. Include: External advice only. "
            f"This is not authorization."
        )
    return (
        f"Upload or paste the complete package.md file shown above into a fresh chat "
        f"with {advisor}. The advisor cannot resolve the local task id {task_id} by "
        f"itself. Bring the full answer back to Codex for review."
    )


def title_from_question(question: str) -> str:
    stripped = " ".join(question.strip().split())
    return stripped[:80] or "Advisor Consultation"


def unique_task_id(tasks_root: Path, title: str) -> str:
    base = slugify(title) or "advisor-consultation"
    candidate = base[:64].strip("-") or "advisor-consultation"
    if not (tasks_root / candidate).exists():
        return candidate
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{candidate[:48].strip('-')}-{suffix}"


def slugify(value: str) -> str:
    slug = SLUG_RE.sub("-", value.lower()).strip("-")
    return re.sub(r"-+", "-", slug)


def resolve_language(language: str, title: str, question: str) -> str:
    if language != "auto":
        return language
    return "zh" if ZH_RE.search(f"{title}\n{question}") else "en"


def validate_task_id(task_id: str) -> None:
    if not TASK_ID_RE.fullmatch(task_id):
        raise ValueError("task_id must be a lowercase slug using letters, numbers, and hyphens")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def risk_level(mode: str) -> str:
    if mode == "ask-first":
        return "1/5"
    return "1/5 local-only or 3/5 while public Auto MCP tunnel is active"


def disallowed_inputs(mode: str) -> List[str]:
    return [
        "secrets",
        "credentials",
        "browser data",
        "automatic implementation",
        "real project files",
        "shell commands",
        "Git operations",
        "dependency installation",
    ]


def next_local_action(mode: str, advisor_channel: str, task_id: str) -> str:
    if advisor_channel == "direct-tool":
        return f"Call the visible advisor tool/connector for task {task_id}, then import advice."
    if advisor_channel == "browser-automation":
        return f"Use authorized browser/computer automation to send task {task_id}, then import advice."
    if mode == "auto-mcp":
        return (
            f"Open Auto MCP window, then ask ChatGPT Web to read task {task_id} and submit advice; "
            f"if Codex has no advisor channel, wait for user-web or automation authorization."
        )
    return (
        f"Upload or paste the complete package.md for task {task_id} into the advisor, "
        f"then bring the full answer back to Codex for Import Mode review."
    )


if __name__ == "__main__":
    raise SystemExit(main())
