from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from trusted_tasks import PROJECT_ROOT


LOG_ROOT = (
    PROJECT_ROOT
    / "logs"
).resolve()

OUTPUT_ROOT = (
    PROJECT_ROOT
    / "outputs"
).resolve()


def resolve_allowed_path(
    value: str | Path,
    *,
    allowed_root: str | Path,
    base_directory: str | Path = PROJECT_ROOT,
) -> Path:
    """
    Resolve a path and verify that it remains inside an allowed
    directory.

    This prevents the UI from reading arbitrary files from the
    computer.
    """
    root = Path(
        allowed_root
    ).expanduser().resolve()

    candidate = Path(
        value
    ).expanduser()

    if not candidate.is_absolute():
        candidate = (
            Path(base_directory)
            / candidate
        )

    candidate = candidate.resolve()

    if (
        candidate != root
        and root not in candidate.parents
    ):
        raise ValueError(
            f"Path is outside the allowed directory: {candidate}"
        )

    return candidate


def read_log_tail(
    log_path: str | Path,
    *,
    maximum_characters: int = 12_000,
    log_root: str | Path = LOG_ROOT,
) -> str:
    """
    Read only the end of a worker log.

    Limiting the number of characters prevents a large log from
    overwhelming the Streamlit page.
    """
    if maximum_characters < 1:
        raise ValueError(
            "maximum_characters must be at least one."
        )

    path = resolve_allowed_path(
        log_path,
        allowed_root=log_root,
    )

    if not path.exists():
        return (
            f"Log file does not exist: {path}"
        )

    if not path.is_file():
        return (
            f"Log path is not a file: {path}"
        )

    content = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    if len(content) <= maximum_characters:
        return content

    return (
        "[Earlier log content omitted]\n\n"
        + content[-maximum_characters:]
    )


def extract_output_paths(
    log_content: str,
    *,
    output_root: str | Path = OUTPUT_ROOT,
) -> list[Path]:
    """
    Extract safe output paths printed by trusted workloads.

    Expected log line:

        Output written to /path/to/output.json
    """
    raw_paths = re.findall(
        r"^Output written to\s+(.+?)\s*$",
        log_content,
        flags=re.MULTILINE,
    )

    safe_paths: list[Path] = []
    seen_paths: set[Path] = set()

    for raw_path in raw_paths:
        try:
            path = resolve_allowed_path(
                raw_path.strip(),
                allowed_root=output_root,
            )
        except ValueError:
            continue

        if (
            path.exists()
            and path.is_file()
            and path not in seen_paths
        ):
            safe_paths.append(path)
            seen_paths.add(path)

    return safe_paths


def summarise_output_file(
    output_path: str | Path,
    *,
    output_root: str | Path = OUTPUT_ROOT,
) -> dict[str, Any] | None:
    """
    Return a small summary for a generated JSON output file.
    """
    path = resolve_allowed_path(
        output_path,
        allowed_root=output_root,
    )

    if (
        not path.exists()
        or not path.is_file()
        or path.suffix.lower() != ".json"
    ):
        return None

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        json.JSONDecodeError,
        OSError,
    ):
        return None

    if not isinstance(payload, dict):
        return None

    summary_keys = [
        "task",
        "items_processed",
        "started_at",
        "finished_at",
    ]

    summary = {
        key: payload[key]
        for key in summary_keys
        if key in payload
    }

    return summary or None
