from __future__ import annotations

import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from statement_sorter.categorize import RuleError, categorize_transactions, load_rules
from statement_sorter.export import write_csv
from statement_sorter.models import CSV_COLUMNS
from statement_sorter.parser import parse_transactions, split_transaction_blocks


FIXTURE_TEXT = """
Statement header
01/05/2026 SALARY ACME SDN BHD
PAYROLL MAY
5,000.00 15,000.00
02/05/2026 SHOPEE MALAYSIA
ORDER 12345
120.50 14,879.50
03/05/2026 UNKNOWN MERCHANT
SOMETHING TO CHECK
77.00 14,802.50
"""

HSBC_OCR_DATE_VARIANTS = """
BALANCE BROUGHT FORWARD 20,000.00
O6Apr2026 QR PAYMENT
CAFE TEST
12.00 19,988.00
O7Apr2026
HOTLINK PREPAID
30.00 19,958.00
_O8Apr2026__|FPX-GPAY NETWORK
10.00 19,948.00
O9Apr2026  /QR PAYMENT
15.00 19,933.00
10Apr2026 {QR PAYMENT
20.00 19,913.00
O03May2026 )QR PAYMENT
11.00 19,902.00
04May2026 )QR PAYMENT
7.00 19,895.00
BALANCE CARRIED FORWARD 19,895.00
CLOSING BALANCE 19,895.00
"""

FALSE_POSITIVE_OCR_LINES = """
Statement Date O6MAY2026
Customer Number O7Apr2026
Sequence Number 10Apr2026
Summary of Your Portfolio O03May2026
DEPOSITS AND INVESTMENTS 04May2026
TOTAL DEPOSITS O8Apr2026
Account Number 09Apr2026
Page 1 of 8 O9Apr2026
MEPS-29APR2026 15:28:23
O7Apr2026 |FPX-HOTLINK TOP UP
30.00 19,958.00
10Apr2026 {QR PAYMENT
20.00 19,938.00
O03May2026 )QR PAYMENT
11.00 19,927.00
"""

ACCOUNT_SUMMARY_WITH_DATE = """
O6Apr2026 4617 7290 2663 3785 DR=Debit DEMAND DEPOSITS
CREDIT/CHARGE TOTAL DEPOSITS AND INVESTMENTS 20,000.00
O7Apr2026 |FPX-HOTLINK TOP UP
30.00 19,970.00
"""

RUNNING_BALANCE_TEXT = """
BALANCE BROUGHT FORWARD 17199.09
O7Apr2026 |FPX-HOTLINK TOP UP
10.00 17189.09
O9Apr2026  /QR PAYMENT
19.00 16939.49 16920.49
10Apr2026 SALARY ACME SDN BHD
500.00 17420.49
O03May2026 )QR PAYMENT
something without money
"""

INTERMEDIATE_BALANCE_TEXT = """
BALANCE BROUGHT FORWARD 16939.49
O9Apr2026  /QR PAYMENT
19.00 16939.49 16920.49
"""

REAL_OUTPUT_SHAPE_TEXT = """
BALANCE BROUGHT FORWARD 17,199.09
O7Apr2026 |FPX-HOTLINK TOP UP
10.00 0.00 17,189.09
"""

SAME_DAY_TWO_QR_PAYMENTS = """
BALANCE BROUGHT FORWARD 100.00
O8Apr2026 QR PAYMENT CAFE ONE
10.00 90.00
QR PAYMENT CAFE TWO
20.00 70.00
"""

SAME_DAY_VISA_AND_QR = """
BALANCE BROUGHT FORWARD 200.00
14Apr2026 VISA POS SHOPEE
30.00 170.00
QR PAYMENT DINNER
5.00 165.00
"""


class ParserTests(unittest.TestCase):
    def test_splits_from_date_to_next_date_as_blocks(self) -> None:
        blocks = split_transaction_blocks(FIXTURE_TEXT)

        self.assertEqual(len(blocks), 3)
        self.assertIn("PAYROLL MAY", "\n".join(blocks[0]))
        self.assertNotIn("SHOPEE", "\n".join(blocks[0]))

    def test_parses_multiline_description_and_raw_text(self) -> None:
        transactions = parse_transactions(FIXTURE_TEXT)

        self.assertEqual(transactions[0].date, "2026-05-01")
        self.assertIn("SALARY ACME SDN BHD", transactions[0].description)
        self.assertIn("PAYROLL MAY", transactions[0].description)
        self.assertIn("PAYROLL MAY", transactions[0].raw_text)
        self.assertEqual(transactions[0].balance, "15,000.00")

    def test_detects_hsbc_ocr_compact_date_variants_near_line_start(self) -> None:
        transactions = parse_transactions(HSBC_OCR_DATE_VARIANTS)

        self.assertEqual(
            [transaction.date for transaction in transactions],
            [
                "2026-04-06",
                "2026-04-07",
                "2026-04-08",
                "2026-04-09",
                "2026-04-10",
                "2026-05-03",
                "2026-05-04",
            ],
        )
        self.assertEqual(len(transactions), 7)
        self.assertIn("FPX-GPAY NETWORK", transactions[2].description)
        self.assertIn("O8Apr2026__|FPX-GPAY NETWORK", transactions[2].raw_text)

    def test_balance_lines_are_not_transaction_blocks(self) -> None:
        blocks = split_transaction_blocks(HSBC_OCR_DATE_VARIANTS)
        joined_blocks = "\n\n".join("\n".join(block) for block in blocks)

        self.assertNotIn("BALANCE BROUGHT FORWARD", joined_blocks)
        self.assertNotIn("BALANCE CARRIED FORWARD", joined_blocks)
        self.assertNotIn("CLOSING BALANCE", joined_blocks)

    def test_ignores_statement_headers_portfolio_lines_and_midline_dates(self) -> None:
        transactions = parse_transactions(FALSE_POSITIVE_OCR_LINES)

        self.assertEqual(
            [transaction.date for transaction in transactions],
            ["2026-04-07", "2026-04-10", "2026-05-03"],
        )
        joined_raw_text = "\n".join(transaction.raw_text for transaction in transactions)
        self.assertNotIn("Statement Date O6MAY2026", joined_raw_text)
        self.assertNotIn("MEPS-29APR2026", joined_raw_text)

    def test_does_not_start_block_from_date_after_unapproved_leading_text(self) -> None:
        transactions = parse_transactions(
            """
            MEPS-29APR2026 15:28:23
            O7Apr2026 |FPX-HOTLINK TOP UP
            30.00 19,958.00
            """
        )

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].date, "2026-04-07")
        self.assertNotIn("MEPS-29APR2026", transactions[0].raw_text)

    def test_excludes_account_summary_block_even_when_it_contains_date(self) -> None:
        transactions = parse_transactions(ACCOUNT_SUMMARY_WITH_DATE)

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].date, "2026-04-07")
        self.assertIn("FPX-HOTLINK TOP UP", transactions[0].description)
        self.assertNotIn("DEMAND DEPOSITS", transactions[0].raw_text)

    def test_infers_withdrawal_from_running_balance(self) -> None:
        transaction = parse_transactions(RUNNING_BALANCE_TEXT)[0]

        self.assertEqual(transaction.date, "2026-04-07")
        self.assertEqual(transaction.money_out, "10.00")
        self.assertEqual(transaction.money_in, "")
        self.assertEqual(transaction.balance, "17189.09")

    def test_infers_withdrawal_when_intermediate_balance_is_present(self) -> None:
        transaction = parse_transactions(INTERMEDIATE_BALANCE_TEXT)[0]

        self.assertEqual(transaction.date, "2026-04-09")
        self.assertEqual(transaction.money_out, "19.00")
        self.assertEqual(transaction.money_in, "")
        self.assertEqual(transaction.balance, "16920.49")

    def test_infers_deposit_from_running_balance(self) -> None:
        transaction = parse_transactions(RUNNING_BALANCE_TEXT)[2]

        self.assertEqual(transaction.date, "2026-04-10")
        self.assertEqual(transaction.money_in, "500.00")
        self.assertEqual(transaction.money_out, "")
        self.assertEqual(transaction.balance, "17420.49")

    def test_missing_money_fields_are_empty_strings_not_zeroes(self) -> None:
        transaction = parse_transactions(RUNNING_BALANCE_TEXT)[3]

        self.assertEqual(transaction.date, "2026-05-03")
        self.assertEqual(transaction.money_in, "")
        self.assertEqual(transaction.money_out, "")
        self.assertNotEqual(transaction.money_in, "0.00")
        self.assertNotEqual(transaction.money_out, "0.00")
        self.assertIn("no_amount", transaction.review_reasons)

    def test_running_balance_ignores_zero_money_column(self) -> None:
        transactions = parse_transactions(REAL_OUTPUT_SHAPE_TEXT)

        self.assertEqual(transactions[0].description, "FPX-HOTLINK TOP UP")
        self.assertEqual(transactions[0].money_out, "10.00")
        self.assertEqual(transactions[0].money_in, "")
        self.assertEqual(transactions[0].balance, "17,189.09")

    def test_running_balance_ignores_intermediate_balance_column(self) -> None:
        transaction = parse_transactions(INTERMEDIATE_BALANCE_TEXT)[0]

        self.assertEqual(transaction.description, "QR PAYMENT")
        self.assertEqual(transaction.money_out, "19.00")
        self.assertEqual(transaction.money_in, "")
        self.assertEqual(transaction.balance, "16920.49")

    def test_splits_same_day_repeated_qr_payment_markers(self) -> None:
        transactions = parse_transactions(SAME_DAY_TWO_QR_PAYMENTS)

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].date, "2026-04-08")
        self.assertEqual(transactions[0].description, "QR PAYMENT CAFE ONE")
        self.assertEqual(transactions[0].money_out, "10.00")
        self.assertEqual(transactions[0].balance, "90.00")
        self.assertEqual(transactions[1].date, "2026-04-08")
        self.assertEqual(transactions[1].description, "QR PAYMENT CAFE TWO")
        self.assertEqual(transactions[1].money_out, "20.00")
        self.assertEqual(transactions[1].balance, "70.00")
        self.assertIn("QR PAYMENT CAFE TWO", transactions[1].raw_text)
        self.assertNotIn("QR PAYMENT CAFE ONE", transactions[1].raw_text)

    def test_splits_same_day_visa_pos_followed_by_qr_payment(self) -> None:
        transactions = parse_transactions(SAME_DAY_VISA_AND_QR)

        self.assertEqual(len(transactions), 2)
        self.assertEqual([transaction.date for transaction in transactions], ["2026-04-14", "2026-04-14"])
        self.assertEqual(transactions[0].description, "VISA POS SHOPEE")
        self.assertEqual(transactions[0].money_out, "30.00")
        self.assertEqual(transactions[1].description, "QR PAYMENT DINNER")
        self.assertEqual(transactions[1].money_out, "5.00")

    def test_single_transaction_block_behavior_does_not_regress(self) -> None:
        transactions = parse_transactions(REAL_OUTPUT_SHAPE_TEXT)

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].description, "FPX-HOTLINK TOP UP")
        self.assertEqual(transactions[0].money_out, "10.00")


class CategorizerTests(unittest.TestCase):
    def test_rules_match_case_insensitively_and_set_review_for_uncertain_amounts(self) -> None:
        rules = [
            {"pattern": "salary", "category": "Income", "treatment": "income"},
            {"pattern": "SHOPEE", "category": "Shopping", "treatment": "expense"},
        ]
        transactions = categorize_transactions(parse_transactions(FIXTURE_TEXT), rules)

        self.assertEqual(transactions[0].category, "Income")
        self.assertEqual(transactions[0].treatment, "income")
        self.assertEqual(transactions[0].money_in, "")
        self.assertEqual(transactions[0].money_out, "")
        self.assertEqual(transactions[0].status, "review")

        self.assertEqual(transactions[1].category, "Shopping")
        self.assertEqual(transactions[1].treatment, "expense")
        self.assertEqual(transactions[1].money_in, "")
        self.assertEqual(transactions[1].money_out, "120.50")

        self.assertEqual(transactions[2].category, "Other")
        self.assertEqual(transactions[2].treatment, "unknown")
        self.assertEqual(transactions[2].status, "review")

    def test_rejects_invalid_treatment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "rules.yml"
            path.write_text(
                "rules:\n"
                "  - pattern: \"X\"\n"
                "    category: \"Bad\"\n"
                "    treatment: \"bad\"\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuleError):
                load_rules(path)


class ExportTests(unittest.TestCase):
    def test_csv_header_order_is_fixed(self) -> None:
        rules = [{"pattern": "SHOPEE", "category": "Shopping", "treatment": "expense"}]
        transactions = categorize_transactions(parse_transactions(FIXTURE_TEXT), rules)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "statement.csv"
            write_csv(transactions, path)

            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader)

        self.assertEqual(header, CSV_COLUMNS)


if __name__ == "__main__":
    unittest.main()
