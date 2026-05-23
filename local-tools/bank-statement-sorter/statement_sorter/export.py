from __future__ import annotations

import csv
from pathlib import Path

from .models import CSV_COLUMNS, Transaction


def write_csv(transactions: list[Transaction], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for transaction in transactions:
            writer.writerow(transaction.to_csv_row())
