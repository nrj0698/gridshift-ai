from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time


def create_vector(
    text: str,
    dimensions: int = 16,
) -> list[float]:
    """
    Create a deterministic demonstration vector from text.

    This is not a production embedding model. It gives the
    worker a safe, reproducible batch-processing task.
    """
    digest = hashlib.sha256(
        text.encode("utf-8")
    ).digest()

    raw_values = [
        digest[index] / 255
        for index in range(dimensions)
    ]

    magnitude = math.sqrt(
        sum(
            value * value
            for value in raw_values
        )
    )

    if magnitude == 0:
        return raw_values

    return [
        round(
            value / magnitude,
            6,
        )
        for value in raw_values
    ]


def run_batch(
    items: int,
    output_directory: Path,
) -> Path:
    """
    Process sample records and save the resulting vectors.
    """
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    started_at = datetime.now(
        timezone.utc
    )

    print(
        f"Starting demo AI batch with {items} items.",
        flush=True,
    )

    records = []

    for item_number in range(
        1,
        items + 1,
    ):
        text = (
            f"Sample product record "
            f"{item_number}"
        )

        records.append(
            {
                "id": item_number,
                "text": text,
                "vector": create_vector(text),
            }
        )

        if (
            item_number == 1
            or item_number % 5 == 0
            or item_number == items
        ):
            print(
                f"Processed {item_number}/{items}",
                flush=True,
            )

        time.sleep(0.05)

    finished_at = datetime.now(
        timezone.utc
    )

    timestamp = started_at.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_path = (
        output_directory
        / f"demo_ai_batch_{timestamp}.json"
    )

    output_payload = {
        "task": "demo_ai_batch",
        "items_processed": items,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "records": records,
    }

    output_path.write_text(
        json.dumps(
            output_payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"Output written to {output_path}",
        flush=True,
    )

    print(
        "Demo AI batch completed successfully.",
        flush=True,
    )

    return output_path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run GridShift's trusted demonstration "
            "AI batch workload."
        )
    )

    parser.add_argument(
        "--items",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )

    arguments = parser.parse_args()

    if not 1 <= arguments.items <= 1000:
        parser.error(
            "--items must be between 1 and 1000"
        )

    return arguments


def main() -> None:
    arguments = parse_arguments()

    run_batch(
        items=arguments.items,
        output_directory=(
            arguments.output_dir
        ),
    )


if __name__ == "__main__":
    main()
