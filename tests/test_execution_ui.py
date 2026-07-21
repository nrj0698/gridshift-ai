from pathlib import Path

import pytest

from execution_ui import (
    extract_output_paths,
    read_log_tail,
    resolve_allowed_path,
    summarise_output_file,
)


def test_resolves_path_inside_allowed_directory(
    tmp_path,
) -> None:
    allowed_root = (
        tmp_path
        / "logs"
    )

    allowed_root.mkdir()

    log_file = (
        allowed_root
        / "run.log"
    )

    log_file.write_text(
        "Worker completed.",
        encoding="utf-8",
    )

    resolved = resolve_allowed_path(
        log_file,
        allowed_root=allowed_root,
    )

    assert resolved == log_file.resolve()


def test_rejects_path_outside_allowed_directory(
    tmp_path,
) -> None:
    allowed_root = (
        tmp_path
        / "logs"
    )

    allowed_root.mkdir()

    outside_file = (
        tmp_path
        / "secret.txt"
    )

    outside_file.write_text(
        "secret",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="outside the allowed directory",
    ):
        resolve_allowed_path(
            outside_file,
            allowed_root=allowed_root,
        )


def test_reads_only_log_tail(
    tmp_path,
) -> None:
    log_root = (
        tmp_path
        / "logs"
    )

    log_root.mkdir()

    log_file = (
        log_root
        / "run.log"
    )

    log_file.write_text(
        "abcdefghij",
        encoding="utf-8",
    )

    result = read_log_tail(
        log_file,
        maximum_characters=4,
        log_root=log_root,
    )

    assert result.endswith(
        "ghij"
    )

    assert "Earlier log content omitted" in result


def test_extracts_safe_output_path(
    tmp_path,
) -> None:
    output_root = (
        tmp_path
        / "outputs"
    )

    output_root.mkdir()

    output_file = (
        output_root
        / "result.json"
    )

    output_file.write_text(
        '{"items_processed": 5}',
        encoding="utf-8",
    )

    log_content = (
        f"Output written to {output_file}\n"
    )

    result = extract_output_paths(
        log_content,
        output_root=output_root,
    )

    assert result == [
        output_file.resolve()
    ]


def test_ignores_output_path_outside_allowed_directory(
    tmp_path,
) -> None:
    output_root = (
        tmp_path
        / "outputs"
    )

    output_root.mkdir()

    outside_file = (
        tmp_path
        / "outside.json"
    )

    outside_file.write_text(
        "{}",
        encoding="utf-8",
    )

    log_content = (
        f"Output written to {outside_file}\n"
    )

    result = extract_output_paths(
        log_content,
        output_root=output_root,
    )

    assert result == []


def test_summarises_json_output(
    tmp_path,
) -> None:
    output_root = (
        tmp_path
        / "outputs"
    )

    output_root.mkdir()

    output_file = (
        output_root
        / "result.json"
    )

    output_file.write_text(
        """
        {
            "task": "demo_ai_batch",
            "items_processed": 12,
            "started_at": "2026-07-21T10:00:00Z",
            "finished_at": "2026-07-21T10:01:00Z",
            "records": []
        }
        """,
        encoding="utf-8",
    )

    result = summarise_output_file(
        output_file,
        output_root=output_root,
    )

    assert result is not None
    assert result["task"] == "demo_ai_batch"
    assert result["items_processed"] == 12
    assert "records" not in result
