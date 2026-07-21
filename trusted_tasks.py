from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import sys


PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class TaskDefinition:
    """
    One local task that the GridShift worker is allowed to run.
    """

    task_id: str
    label: str
    description: str
    timeout_seconds: int
    command_builder: Callable[
        [dict[str, object]],
        list[str],
    ]


def _build_demo_ai_batch_command(
    parameters: dict[str, object],
) -> list[str]:
    """
    Build the command for the safe demo AI batch workload.
    """
    allowed_parameters = {
        "items",
    }

    unknown_parameters = (
        set(parameters)
        - allowed_parameters
    )

    if unknown_parameters:
        unknown_text = ", ".join(
            sorted(unknown_parameters)
        )

        raise ValueError(
            "Unsupported demo task parameters: "
            f"{unknown_text}"
        )

    raw_items = parameters.get(
        "items",
        20,
    )

    if isinstance(raw_items, bool):
        raise ValueError(
            "items must be an integer."
        )

    try:
        items = int(raw_items)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "items must be an integer."
        ) from error

    if not 1 <= items <= 1000:
        raise ValueError(
            "items must be between 1 and 1000."
        )

    workload_script = (
        PROJECT_ROOT
        / "workloads"
        / "demo_ai_batch.py"
    )

    output_directory = (
        PROJECT_ROOT
        / "outputs"
    )

    return [
        sys.executable,
        str(workload_script),
        "--items",
        str(items),
        "--output-dir",
        str(output_directory),
    ]


TRUSTED_TASKS: dict[
    str,
    TaskDefinition,
] = {
    "demo_ai_batch": TaskDefinition(
        task_id="demo_ai_batch",
        label="Demo AI batch processing",
        description=(
            "Processes sample records and creates deterministic "
            "vector representations."
        ),
        timeout_seconds=300,
        command_builder=(
            _build_demo_ai_batch_command
        ),
    ),
}


def list_trusted_tasks() -> tuple[
    TaskDefinition,
    ...,
]:
    """
    Return all tasks that the worker may execute.
    """
    return tuple(
        TRUSTED_TASKS.values()
    )


def get_trusted_task(
    task_id: str,
) -> TaskDefinition:
    """
    Retrieve one trusted task definition.
    """
    clean_task_id = task_id.strip()

    try:
        return TRUSTED_TASKS[
            clean_task_id
        ]
    except KeyError as error:
        raise ValueError(
            f"Unknown or untrusted task: {task_id}"
        ) from error


def build_trusted_command(
    task_id: str,
    parameters: dict[str, object] | None = None,
) -> list[str]:
    """
    Build a safe argument list for a trusted task.

    The returned command is intended for subprocess with
    shell=False.
    """
    task = get_trusted_task(task_id)

    clean_parameters = (
        parameters.copy()
        if parameters is not None
        else {}
    )

    command = task.command_builder(
        clean_parameters
    )

    if not command:
        raise ValueError(
            "The trusted task produced an empty command."
        )

    return command
