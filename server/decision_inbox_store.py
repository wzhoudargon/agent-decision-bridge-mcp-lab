"""File-backed Decision Inbox store for package-only MCP v1."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


TASK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ADVISOR_SLUG_RE = re.compile(r"[^a-z0-9-]+")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$")
NOT_AUTHORIZATION_MARKERS = (
    "not authorization",
    "not user authorization",
    "not local authorization",
    "not execution authorization",
    "external advice only",
    "advice, not authorization",
    "不是授权",
    "不代表授权",
    "非授权",
    "不构成授权",
)


class DecisionInboxError(Exception):
    """Base class for Decision Inbox store errors."""


class AccessDenied(DecisionInboxError):
    """Raised when a task id or path would escape the inbox contract."""


class TaskNotFound(DecisionInboxError):
    """Raised when a valid task id does not exist."""


class MetadataError(DecisionInboxError):
    """Raised when task metadata is missing or inconsistent."""


class DecisionInboxStore:
    def __init__(self, tasks_root: Path):
        self.tasks_root = tasks_root.resolve(strict=True)
        if not self.tasks_root.is_dir():
            raise ValueError(f"Tasks root is not a directory: {tasks_root}")

    def list_decision_tasks(self) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []
        for path in sorted(self.tasks_root.iterdir(), key=lambda item: item.name):
            if not path.is_dir() or path.name.startswith("_") or path.name.startswith("."):
                continue
            if not TASK_ID_RE.fullmatch(path.name):
                continue
            try:
                metadata = self._read_metadata(path.name)
            except DecisionInboxError:
                continue
            tasks.append(self._task_summary(metadata, path.name))
        return tasks

    def get_decision_package(self, task_id: str) -> str:
        task_dir = self._task_dir(task_id)
        package_path = task_dir / "package.md"
        if not package_path.is_file():
            raise TaskNotFound(f"Missing package.md for task: {task_id}")
        return package_path.read_text(encoding="utf-8")

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        task_dir = self._task_dir(task_id)
        metadata = self._read_metadata(task_id)
        summary = self._task_summary(metadata, task_id)
        summary["advice_count"] = self._count_markdown_files(task_dir / "advice")
        summary["fact_check_request_count"] = self._count_markdown_files(
            task_dir / "fact-check-requests"
        )
        summary["has_package"] = (task_dir / "package.md").is_file()
        return summary

    def submit_advice(
        self,
        task_id: str,
        advisor: str,
        content: str,
        timestamp: Optional[str] = None,
    ) -> Dict[str, str]:
        task_dir = self._task_dir(task_id)
        advisor_name = self._require_advisor(advisor)
        self._require_non_empty_content(content)
        self._require_not_authorization_marker(content)
        submitted_at = self._timestamp(timestamp)
        file_name = f"{submitted_at}-{self._advisor_slug(advisor_name)}.md"
        target = task_dir / "advice" / file_name
        result = self._write_markdown_exclusive(target, content)
        result.update(
            {
                "task_id": task_id,
                "advisor": advisor_name,
                "timestamp": submitted_at,
                "not_authorization": "required_marker_present",
            }
        )
        return result

    def request_local_fact_check(
        self, task_id: str, content: str, timestamp: Optional[str] = None
    ) -> Dict[str, str]:
        task_dir = self._task_dir(task_id)
        self._require_non_empty_content(content)
        target = task_dir / "fact-check-requests" / f"{self._timestamp(timestamp)}.md"
        return self._write_markdown_exclusive(target, content)

    def _task_summary(self, metadata: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "title": str(metadata.get("title", "")),
            "status": str(metadata.get("status", "")),
            "advisor_rounds": int(metadata.get("advisor_rounds", 0)),
            "risk_level": str(metadata.get("risk_level", "")),
            "next_local_action": str(metadata.get("next_local_action", "")),
        }

    def _task_dir(self, task_id: str) -> Path:
        self._validate_task_id(task_id)
        task_dir = (self.tasks_root / task_id).resolve(strict=False)
        if task_dir.parent != self.tasks_root:
            raise AccessDenied("Task path escapes decision-inbox/tasks")
        if not task_dir.is_dir():
            raise TaskNotFound(f"Task not found: {task_id}")
        return task_dir

    def _read_metadata(self, task_id: str) -> Dict[str, Any]:
        task_dir = self._task_dir(task_id)
        metadata_path = task_dir / "metadata.json"
        if not metadata_path.is_file():
            raise MetadataError(f"Missing metadata.json for task: {task_id}")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MetadataError(f"Invalid metadata.json for task: {task_id}") from exc
        if metadata.get("task_id") != task_id:
            raise MetadataError("metadata task_id does not match directory name")
        return metadata

    def _write_markdown_exclusive(self, target: Path, content: str) -> Dict[str, str]:
        resolved_parent = target.parent.resolve(strict=True)
        if resolved_parent.parent.parent != self.tasks_root:
            raise AccessDenied("Write target escapes decision task directory")
        if resolved_parent.name not in ("advice", "fact-check-requests"):
            raise AccessDenied("Writes are allowed only under advice/ or fact-check-requests/")
        if target.suffix != ".md" or target.name.startswith("."):
            raise AccessDenied("Only visible Markdown files may be created")
        with target.open("x", encoding="utf-8") as handle:
            handle.write(content)
        return {"relative_path": target.relative_to(self.tasks_root).as_posix()}

    def _validate_task_id(self, task_id: str) -> None:
        if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
            raise AccessDenied("Task id must be a lowercase slug using letters, numbers, and hyphens")

    def _timestamp(self, timestamp: Optional[str]) -> str:
        if timestamp is None:
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        if not isinstance(timestamp, str) or not TIMESTAMP_RE.fullmatch(timestamp):
            raise AccessDenied("Timestamp must use YYYY-MM-DDTHH-MM-SSZ")
        return timestamp

    def _advisor_slug(self, advisor: str) -> str:
        slug = ADVISOR_SLUG_RE.sub("-", advisor.lower().strip()).strip("-")
        return slug or "unknown-advisor"

    def _require_advisor(self, advisor: str) -> str:
        if not isinstance(advisor, str) or not advisor.strip():
            raise ValueError("advisor must be a non-empty string")
        return advisor.strip()

    def _require_non_empty_content(self, content: str) -> None:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Markdown content must be a non-empty string")

    def _require_not_authorization_marker(self, content: str) -> None:
        normalized = content.lower()
        if not any(marker in normalized for marker in NOT_AUTHORIZATION_MARKERS):
            raise ValueError(
                "submit_advice content must explicitly state that external advice is not authorization"
            )

    def _count_markdown_files(self, folder: Path) -> int:
        if not folder.is_dir():
            return 0
        return sum(1 for path in folder.iterdir() if path.is_file() and path.suffix == ".md")


def default_tasks_root() -> Path:
    return Path(__file__).resolve().parents[1] / "decision-inbox" / "tasks"
