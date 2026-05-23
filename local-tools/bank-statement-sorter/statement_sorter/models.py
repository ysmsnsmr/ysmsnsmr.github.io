from __future__ import annotations

from dataclasses import dataclass, field


CSV_COLUMNS = [
    "date",
    "description",
    "money_in",
    "money_out",
    "balance",
    "category",
    "treatment",
    "status",
    "raw_text",
]

ALLOWED_TREATMENTS = {"expense", "income", "transfer", "fee", "cash", "unknown"}


@dataclass(frozen=True)
class Transaction:
    date: str
    description: str
    money_in: str = ""
    money_out: str = ""
    balance: str = ""
    category: str = "Other"
    treatment: str = "unknown"
    status: str = "review"
    raw_text: str = ""
    amount: str = ""
    review_reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_csv_row(self) -> dict[str, str]:
        return {
            "date": self.date,
            "description": self.description,
            "money_in": self.money_in,
            "money_out": self.money_out,
            "balance": self.balance,
            "category": self.category,
            "treatment": self.treatment,
            "status": self.status,
            "raw_text": self.raw_text,
        }
