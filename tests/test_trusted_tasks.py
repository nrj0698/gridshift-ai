import pytest

from trusted_tasks import (
    build_trusted_command,
    get_trusted_task,
)


def test_builds_demo_command() -> None:
    command = build_trusted_command(
        "demo_ai_batch",
        {
            "items": 12,
        },
    )

    assert isinstance(
        command,
        list,
    )

    assert "--items" in command
    assert "12" in command

    assert "--output-dir" in command


def test_rejects_unknown_task() -> None:
    with pytest.raises(
        ValueError,
        match="Unknown or untrusted",
    ):
        get_trusted_task(
            "delete_everything"
        )


def test_rejects_unknown_parameter() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported",
    ):
        build_trusted_command(
            "demo_ai_batch",
            {
                "shell_command": "rm -rf /",
            },
        )
