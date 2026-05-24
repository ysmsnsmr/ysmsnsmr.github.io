from __future__ import annotations

import contextlib
import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from statement_sorter.categorize import RuleError, categorize_transactions, load_rules
from statement_sorter.credit_card_parser import parse_transactions as parse_credit_card_transactions
from statement_sorter.export import write_csv
from statement_sorter.models import CSV_COLUMNS
from statement_sorter.monthly_summary import (
    build_monthly_summaries,
    _clean_description_for_display,
    main as monthly_summary_main,
    read_statement_csv as read_monthly_csv,
    read_statement_csvs as read_monthly_csvs,
    render_monthly_summary,
    write_monthly_summary,
)
from statement_sorter.parser import parse_transactions, split_transaction_blocks
from statement_sorter.review_report import (
    main as review_report_main,
    read_statement_csv as read_report_csv,
    render_review_report,
    review_reasons,
    write_review_report,
)
from statement_sorter.suggest_rules import (
    read_statement_csv,
    suggest_rule_candidates,
    write_candidate_yaml,
)
from statement_sorter.statement_type import is_credit_card_statement


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

BANK_FOOTER_CONTINUATION_TEXT = """
BALANCE BROUGHT FORWARD 100.00
06May2026 QR PAYMENT DINNER
10.00 90.00
END OF STATEMENT
Important notes: long statement footer should not continue the transaction
07May2026 QR PAYMENT AFTER FOOTER
5.00 85.00
"""

BANK_PAGE_ARTIFACT_BOUNDARY_TEXT = """
BALANCE BROUGHT FORWARD 100.00
06May2026 QR PAYMENT DINNER
10.00 90.00
BALANCE CARRIEDFORWARD
HSBC <x> Amanah 013562 Statement Details Re
BALANCE BROUGHTFORWARD
07May2026 QR PAYMENT BREAKFAST
5.00 85.00
"""

BANK_BOUNDARY_THEN_LATER_TRANSACTION_TEXT = """
BALANCE BROUGHT FORWARD 200.00
06May2026 QR PAYMENT FIRST
20.00 180.00
Transaction Turnover Transaction Count 2 38
Protected by PIDM up to RM250K for each depositor
AMANAH ADVANCE A/C-I 015-000000-000
07May2026 QR PAYMENT SECOND
30.00 150.00
"""

BANK_INCOMPLETE_TRANSACTION_CONTINUES_ACROSS_PAGE_BOUNDARY_TEXT = """
BALANCE BROUGHT FORWARD 300.00
06May2026 QR PAYMENT
HIB- 123456789
BALANCE CARRIEDFORWARD 300.00
Page 2
Statement Details
AMANAH ADVANCE A/C-I 015-000000-000 Protected by PIDM up to RM250K for each depositor
MERCHANT AFTER PAGE
REF EB01-11111 20.00 280.00
07May2026 QR PAYMENT SECOND
30.00 250.00
"""

BANK_PAGE_BOUNDARIES_KEEP_EXTRACTIONS_TEXT = """
BALANCE BROUGHT FORWARD 300.00
06May2026 QR PAYMENT FIRST
20.00 280.00
Page 1 of 3
07May2026 QR PAYMENT SECOND
30.00 250.00
BALANCE CARRIED FORWARD 250.00
Statement Details
BALANCE BROUGHT FORWARD 250.00
08May2026 QR PAYMENT THIRD
40.00 210.00
"""

BANK_PIDM_FOOTER_STOP_TEXT = """
BALANCE BROUGHT FORWARD 100.00
06May2026 QR PAYMENT BEFORE FOOTER
10.00 90.00
PIDM footer notice
07May2026 QR PAYMENT AFTER FOOTER
5.00 85.00
"""

CREDIT_CARD_OCR = """
Account Statement
Card Number Statement Date 21 MAY 2026 Page 2
HSBC Amanah Cash Back Summary Minimum Payment & Overlimit Summary (RM)
Your Previous Statement Balance 3,000.00
Post Date Transaction Date Transaction Details Amount
06 MAY 06 MAY PAYMENT - THANK YOU 3,000.00CR
12 APR 11 APR SUKI-YA PARADIGM PETALING JAYA MY 92.50
13 APR 12 APR LONG MERCHANT NAME 10.00
CONTINUED LOCATION MY
15 APR 15 APR CASH BACK EVERYDAY 12.34CR
Your charge(s) for this month RM 102.50
Total credit limit used RM2,111.00CR
"""

CREDIT_CARD_JANUARY_OCR = """
Account Statement
Statement Date 05 JAN 2026 Payment Due Date 25 JAN 2026
Card Number 1234 5678 9012 3456
Minimum Monthly Payment RM100.00
31 DEC 30 DEC YEAR END SHOP MY 45.00
"""

CREDIT_CARD_CASHBACK_SUMMARY_ARTIFACT_OCR = """
Account Statement
Card Number Statement Date 21 MAY 2026 Page 2
HSBC Amanah Cash Back Summary Minimum Payment & Overlimit Summary (RM)
Post Date Transaction Date Transaction Details Amount
16 MAY 16 MAY 99 SPEEDMART-1096 SELANGOR MY 173.95
HSBC statement Cash Back earned Cash Back diperolehi Overlimit Melebihi Had Kredit
Bonus Cash Back Cash Back bonus Page Halaman Amanah MPower Platinum Card-i
17 MAY 17 MAY HEALTH LANE ARA JAYA PETALING JAYA MY 20.00
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

    def test_footer_hard_stop_excludes_footer_and_stops_parsing(self) -> None:
        transactions = parse_transactions(BANK_FOOTER_CONTINUATION_TEXT)

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].date, "2026-05-06")
        self.assertEqual(transactions[0].money_out, "10.00")
        self.assertNotIn("END OF STATEMENT", transactions[0].raw_text)
        self.assertNotIn("Important notes", transactions[0].raw_text)
        self.assertNotIn("AFTER FOOTER", transactions[0].raw_text)

    def test_page_artifact_boundaries_do_not_enter_raw_text_or_description(self) -> None:
        transactions = parse_transactions(BANK_PAGE_ARTIFACT_BOUNDARY_TEXT)

        self.assertEqual(len(transactions), 2)
        self.assertEqual([transaction.date for transaction in transactions], ["2026-05-06", "2026-05-07"])
        self.assertEqual(transactions[0].money_out, "10.00")
        self.assertEqual(transactions[1].money_out, "5.00")
        joined_raw_text = "\n".join(transaction.raw_text for transaction in transactions)
        joined_description = " ".join(transaction.description for transaction in transactions)
        self.assertNotIn("BALANCE CARRIEDFORWARD", joined_raw_text)
        self.assertNotIn("Statement Details", joined_raw_text)
        self.assertNotIn("BALANCE BROUGHTFORWARD", joined_raw_text)
        self.assertNotIn("BALANCE CARRIEDFORWARD", joined_description)
        self.assertNotIn("Statement Details", joined_description)

    def test_boundary_artifact_allows_later_valid_transaction_date(self) -> None:
        transactions = parse_transactions(BANK_BOUNDARY_THEN_LATER_TRANSACTION_TEXT)

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].description, "QR PAYMENT FIRST")
        self.assertEqual(transactions[1].description, "QR PAYMENT SECOND")
        self.assertEqual(transactions[1].money_out, "30.00")
        joined_raw_text = "\n".join(transaction.raw_text for transaction in transactions)
        self.assertNotIn("Transaction Turnover", joined_raw_text)
        self.assertNotIn("AMANAH ADVANCE A/C-I", joined_raw_text)

    def test_incomplete_transaction_continues_across_page_boundary(self) -> None:
        transactions = parse_transactions(BANK_INCOMPLETE_TRANSACTION_CONTINUES_ACROSS_PAGE_BOUNDARY_TEXT)

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].date, "2026-05-06")
        self.assertIn("MERCHANT AFTER PAGE", transactions[0].description)
        self.assertEqual(transactions[0].money_out, "20.00")
        self.assertEqual(transactions[1].date, "2026-05-07")
        joined_raw_text = "\n".join(transaction.raw_text for transaction in transactions)
        self.assertNotIn("BALANCE CARRIEDFORWARD", joined_raw_text)
        self.assertNotIn("Page 2", joined_raw_text)
        self.assertNotIn("Statement Details", joined_raw_text)
        self.assertNotIn("Protected by PIDM", joined_raw_text)

    def test_page_and_balance_boundaries_do_not_collapse_extraction_count(self) -> None:
        transactions = parse_transactions(BANK_PAGE_BOUNDARIES_KEEP_EXTRACTIONS_TEXT)

        self.assertEqual(len(transactions), 3)
        self.assertEqual(
            [transaction.description for transaction in transactions],
            ["QR PAYMENT FIRST", "QR PAYMENT SECOND", "QR PAYMENT THIRD"],
        )
        self.assertEqual([transaction.money_out for transaction in transactions], ["20.00", "30.00", "40.00"])
        joined_raw_text = "\n".join(transaction.raw_text for transaction in transactions)
        self.assertNotIn("Page 1 of 3", joined_raw_text)
        self.assertNotIn("BALANCE CARRIED FORWARD", joined_raw_text)
        self.assertNotIn("Statement Details", joined_raw_text)

    def test_pidm_footer_hard_stop_stops_parsing(self) -> None:
        transactions = parse_transactions(BANK_PIDM_FOOTER_STOP_TEXT)

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].description, "QR PAYMENT BEFORE FOOTER")
        self.assertNotIn("Protected by PIDM", transactions[0].raw_text)
        self.assertNotIn("AFTER FOOTER", transactions[0].raw_text)


class StatementTypeTests(unittest.TestCase):
    def test_detects_hsbc_credit_card_statement(self) -> None:
        self.assertTrue(is_credit_card_statement(CREDIT_CARD_OCR))

    def test_bank_debit_ocr_is_not_detected_as_credit_card(self) -> None:
        self.assertFalse(is_credit_card_statement(HSBC_OCR_DATE_VARIANTS))
        self.assertFalse(is_credit_card_statement(FIXTURE_TEXT))


class CreditCardParserTests(unittest.TestCase):
    def test_parses_credit_card_charges_as_money_out(self) -> None:
        transactions = parse_credit_card_transactions(CREDIT_CARD_OCR)
        charge = transactions[1]

        self.assertEqual(charge.date, "2026-04-11")
        self.assertEqual(charge.description, "SUKI-YA PARADIGM PETALING JAYA MY")
        self.assertEqual(charge.money_out, "92.50")
        self.assertEqual(charge.money_in, "")
        self.assertEqual(charge.balance, "")

    def test_parses_credit_card_cr_rows_as_money_in(self) -> None:
        transactions = parse_credit_card_transactions(CREDIT_CARD_OCR)

        self.assertEqual(transactions[0].description, "PAYMENT - THANK YOU")
        self.assertEqual(transactions[0].date, "2026-05-06")
        self.assertEqual(transactions[0].money_in, "3,000.00")
        self.assertEqual(transactions[0].money_out, "")
        self.assertEqual(transactions[3].description, "CASH BACK EVERYDAY")
        self.assertEqual(transactions[3].money_in, "12.34")

    def test_preserves_transaction_block_raw_text_and_continuation_description(self) -> None:
        transactions = parse_credit_card_transactions(CREDIT_CARD_OCR)
        transaction = transactions[2]

        self.assertEqual(transaction.description, "LONG MERCHANT NAME CONTINUED LOCATION MY")
        self.assertIn("13 APR 12 APR LONG MERCHANT NAME 10.00", transaction.raw_text)
        self.assertIn("CONTINUED LOCATION MY", transaction.raw_text)

    def test_excludes_credit_card_headers_summaries_and_balance_rows(self) -> None:
        transactions = parse_credit_card_transactions(CREDIT_CARD_OCR)
        joined_raw_text = "\n".join(transaction.raw_text for transaction in transactions)

        self.assertEqual(len(transactions), 4)
        self.assertNotIn("Your Previous Statement Balance", joined_raw_text)
        self.assertNotIn("Post Date Transaction Date", joined_raw_text)
        self.assertNotIn("Your charge(s) for this month", joined_raw_text)
        self.assertNotIn("Total credit limit used", joined_raw_text)

    def test_excludes_cashback_summary_artifacts_from_credit_card_transaction_blocks(self) -> None:
        transactions = parse_credit_card_transactions(CREDIT_CARD_CASHBACK_SUMMARY_ARTIFACT_OCR)

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].description, "99 SPEEDMART-1096 SELANGOR MY")
        self.assertEqual(transactions[0].money_out, "173.95")
        self.assertNotIn("Cash Back earned", transactions[0].raw_text)
        self.assertNotIn("Overlimit", transactions[0].raw_text)
        self.assertNotIn("MPower Platinum", transactions[0].raw_text)

    def test_uses_previous_year_for_december_transactions_on_january_statement(self) -> None:
        transactions = parse_credit_card_transactions(CREDIT_CARD_JANUARY_OCR)

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].date, "2025-12-30")
        self.assertEqual(transactions[0].money_out, "45.00")


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


class SuggestRulesTests(unittest.TestCase):
    def test_suggests_candidates_only_from_other_unknown_or_review_rows(self) -> None:
        rows = [
            _csv_row("QR PAYMENT CAFE ALPHA", "12.00", "Other", "unknown", "review"),
            _csv_row("VISA POS BOOK SHOP", "22.50", "Shopping", "expense", "auto"),
            _csv_row("MEPS-ATM CASH", "100.00", "Cash", "cash", "review"),
        ]

        candidates = suggest_rule_candidates(rows, existing_rules=[])

        self.assertEqual([candidate.pattern for candidate in candidates], ["ATM CASH", "CAFE ALPHA"])

    def test_aggregates_candidate_counts_and_amounts(self) -> None:
        rows = [
            _csv_row("QR PAYMENT CAFE ALPHA", "12.00", "Other", "unknown", "review"),
            _csv_row("QR PAYMENT CAFE ALPHA", "8.50", "Other", "unknown", "review"),
            _csv_row("SALARY ACME", "", "Other", "unknown", "review", money_in="500.00"),
        ]

        candidates = suggest_rule_candidates(rows, existing_rules=[])
        qr_candidate = next(candidate for candidate in candidates if candidate.pattern == "CAFE ALPHA")
        salary_candidate = next(candidate for candidate in candidates if candidate.pattern == "SALARY ACME")

        self.assertEqual(qr_candidate.count, 2)
        self.assertEqual(str(qr_candidate.money_out), "20.50")
        self.assertEqual(str(qr_candidate.money_in), "0.00")
        self.assertEqual(salary_candidate.count, 1)
        self.assertEqual(str(salary_candidate.money_in), "500.00")

    def test_existing_rules_are_excluded_and_candidate_yaml_is_loadable(self) -> None:
        rows = [
            _csv_row("VISA POS SHOPEE MARKET", "30.00", "Other", "unknown", "review"),
            _csv_row("QR PAYMENT CAFE BETA", "9.00", "Other", "unknown", "review"),
        ]
        candidates = suggest_rule_candidates(
            rows,
            existing_rules=[{"pattern": "SHOPEE", "category": "Shopping", "treatment": "expense"}],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "rule-candidates.yml"
            write_candidate_yaml(candidates, out_path)
            loaded = load_rules(out_path)

        self.assertEqual([candidate.pattern for candidate in candidates], ["CAFE BETA"])
        self.assertEqual(loaded[0]["pattern"], "CAFE BETA")
        self.assertEqual(loaded[0]["category"], "Other")
        self.assertEqual(loaded[0]["treatment"], "unknown")

    def test_normalizes_qr_payment_references_to_reusable_merchant_patterns(self) -> None:
        rows = [
            _csv_row(
                "QR PAYMENT HIB- 340026277XF 1M5C3K5B RESTORAN MAZEELA BISTRO",
                "15.00",
                "Other",
                "unknown",
                "review",
            ),
            _csv_row(
                "QR PAYMENT HIB- 665497298XNP2NCR1A0 JANS BURGER DWAOR-20260408HBMBMYKL0300QR68872219 REF",
                "9.50",
                "Other",
                "unknown",
                "review",
            ),
        ]

        candidates = suggest_rule_candidates(rows, existing_rules=[])

        self.assertEqual(
            [candidate.pattern for candidate in candidates],
            ["JANS BURGER", "RESTORAN MAZEELA BISTRO"],
        )

    def test_strips_payment_markers_and_preserves_marker_comment(self) -> None:
        rows = [
            _csv_row(
                "QR PAYMENT HIB- 340026277XF 1M5C3K5B RESTORAN MAZEELA BISTRO",
                "15.00",
                "Other",
                "unknown",
                "review",
            ),
        ]
        candidates = suggest_rule_candidates(rows, existing_rules=[])

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "rule-candidates.yml"
            write_candidate_yaml(candidates, out_path)
            output = out_path.read_text(encoding="utf-8")

        self.assertEqual(candidates[0].pattern, "RESTORAN MAZEELA BISTRO")
        self.assertIn('marker="QR PAYMENT"', output)

    def test_normalizes_visa_pos_to_merchant_pattern(self) -> None:
        rows = [
            _csv_row("VISA POS Shopee MY Marketplace", "30.00", "Other", "unknown", "review"),
        ]

        candidates = suggest_rule_candidates(rows, existing_rules=[])

        self.assertEqual([candidate.pattern for candidate in candidates], ["SHOPEE MY MARKETPLACE"])

    def test_multiple_payment_markers_for_same_merchant_collapse(self) -> None:
        rows = [
            _csv_row("QR PAYMENT CAFE ALPHA", "12.00", "Other", "unknown", "review"),
            _csv_row("VISA POS CAFE ALPHA", "8.50", "Other", "unknown", "review"),
            _csv_row("FPX- CAFE ALPHA", "3.00", "Other", "unknown", "review"),
        ]

        candidates = suggest_rule_candidates(rows, existing_rules=[])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].pattern, "CAFE ALPHA")
        self.assertEqual(candidates[0].count, 3)
        self.assertEqual(candidates[0].markers, {"FPX", "QR PAYMENT", "VISA POS"})

    def test_normalizes_credit_card_merchant_locations_and_store_numbers(self) -> None:
        cases = [
            ("99 SPEEDMART-1096 SELANGOR MY", "99 SPEEDMART"),
            ("SUKI-YA 2@PARADIGM 2 PETALING JAYA MY", "SUKI-YA"),
            ("HEALTH LANE ARA JAYA PETALING JAYA MY", "HEALTH LANE"),
            ("TOOT BAGELS & COFFEE KUALALUMPUR MY", "TOOT BAGELS & COFFEE"),
            ("NETFLIX.COM Singapore SG", "NETFLIX.COM"),
            ("WATSON'S PARADIGM MALL SELANGOR MY", "WATSON"),
            ("LOTUS'S PARADIGM PETALING JAYA MY", "LOTUS"),
            ("HARVEY NORMAN-PARADIGM PETALING JAYA MY", "HARVEY NORMAN"),
        ]

        for description, expected_pattern in cases:
            with self.subTest(description=description):
                candidates = suggest_rule_candidates(
                    [_csv_row(description, "10.00", "Other", "unknown", "review")],
                    existing_rules=[],
                )

                self.assertEqual([candidate.pattern for candidate in candidates], [expected_pattern])

    def test_normalizes_credit_card_processor_and_page_artifacts(self) -> None:
        rows = [
            _csv_row("IPY*QUALITAS ACC EVESU SELANGOR MY", "10.00", "Other", "unknown", "review"),
            _csv_row(
                "AMANAH MPOWER PLATINUM CARD-I 1234567890123456",
                "10.00",
                "Other",
                "unknown",
                "review",
            ),
        ]

        candidates = suggest_rule_candidates(rows, existing_rules=[])

        self.assertEqual([candidate.pattern for candidate in candidates], ["QUALITAS"])

    def test_candidate_generation_does_not_modify_existing_rules_file(self) -> None:
        rows = [_csv_row("QR PAYMENT CAFE GAMMA", "11.00", "Other", "unknown", "review")]

        with tempfile.TemporaryDirectory() as tmp_dir:
            rules_path = Path(tmp_dir) / "rules.yml"
            out_path = Path(tmp_dir) / "rule-candidates.yml"
            original_rules = (
                "rules:\n"
                "  - pattern: \"SHOPEE\"\n"
                "    category: \"Shopping\"\n"
                "    treatment: \"expense\"\n"
            )
            rules_path.write_text(original_rules, encoding="utf-8")
            candidates = suggest_rule_candidates(rows, existing_rules=load_rules(rules_path))
            write_candidate_yaml(candidates, out_path)

            self.assertEqual(rules_path.read_text(encoding="utf-8"), original_rules)
            self.assertTrue(out_path.exists())

    def test_reads_statement_csv_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "statement.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerow(_csv_row("QR PAYMENT CAFE DELTA", "7.00", "Other", "unknown", "review"))

            rows = read_statement_csv(csv_path)

        self.assertEqual(rows[0]["description"], "QR PAYMENT CAFE DELTA")


class ReviewReportTests(unittest.TestCase):
    def test_review_reasons_cover_each_review_condition(self) -> None:
        self.assertEqual(review_reasons(_csv_row("KNOWN REVIEW", "1.00", "Dining", "expense", "review")), ["status=review"])
        self.assertEqual(review_reasons(_csv_row("OTHER AUTO", "2.00", "Other", "expense", "auto")), ["category=Other"])
        self.assertEqual(
            review_reasons(_csv_row("UNKNOWN AUTO", "3.00", "Dining", "unknown", "auto")),
            ["treatment=unknown"],
        )
        self.assertEqual(
            review_reasons(_csv_row("MISSING AMOUNT", "", "Dining", "expense", "auto")),
            ["missing amount"],
        )

    def test_markdown_includes_summary_review_table_and_totals(self) -> None:
        rows = [
            _csv_row("AUTO DINING", "1,200.50", "Dining", "expense", "auto"),
            _csv_row("OTHER | MERCHANT", "20.00", "Other", "expense", "auto"),
            _csv_row("UNKNOWN INCOME", "", "Income", "unknown", "review", money_in="2,500.25"),
            _csv_row("MISSING MONEY", "", "Dining", "expense", "auto"),
        ]

        report = render_review_report(rows, "outputs/statement.csv")

        self.assertIn("| Total rows | 4 |", report)
        self.assertIn("| Review rows | 3 |", report)
        self.assertIn("| Auto rows | 3 |", report)
        self.assertIn("| All rows | 2500.25 | 1220.50 |", report)
        self.assertIn("| Review rows | 2500.25 | 20.00 |", report)
        self.assertIn("OTHER \\| MERCHANT", report)
        self.assertIn("status=review, treatment=unknown", report)
        self.assertIn("missing amount", report)

    def test_missing_amount_diagnostics_are_added_to_review_report(self) -> None:
        rows = [
            _review_diagnostic_row(
                "MISSING PREVIOUS BALANCE",
                balance="1,000.00",
                raw_text="QR PAYMENT FIRST MISSING 10.00",
            ),
            _review_diagnostic_row(
                "PREVIOUS GOOD BALANCE",
                money_out="10.00",
                balance="1,000.00",
                raw_text="PREVIOUS GOOD BALANCE 10.00 1,000.00",
            ),
            _review_diagnostic_row(
                "NO AMOUNT CANDIDATES",
                balance="990.00",
                raw_text="QR PAYMENT NO MONEY TEXT",
            ),
            _review_diagnostic_row(
                "SINGLE AMOUNT CANDIDATE",
                balance="980.00",
                raw_text="QR PAYMENT SINGLE 10.00",
            ),
            _review_diagnostic_row(
                "MISSING CURRENT BALANCE",
                balance="",
                raw_text="QR PAYMENT MISSING CURRENT 10.00",
            ),
            _review_diagnostic_row(
                "NON NUMERIC CURRENT BALANCE",
                balance="not-a-balance",
                raw_text="QR PAYMENT BAD CURRENT 10.00",
            ),
            _review_diagnostic_row(
                "PREVIOUS NON NUMERIC BALANCE",
                money_out="1.00",
                balance="not-a-balance",
                raw_text="PREVIOUS BAD BALANCE 1.00",
            ),
            _review_diagnostic_row(
                "CURRENT AFTER BAD PREVIOUS",
                balance="950.00",
                raw_text="QR PAYMENT AFTER BAD 10.00",
            ),
            _review_diagnostic_row(
                "BALANCE DELTA MISMATCH",
                balance="900.00",
                raw_text="QR PAYMENT MISMATCH 10.00 900.00",
            ),
            _review_diagnostic_row(
                "MULTIPLE MARKERS",
                balance="890.00",
                raw_text="QR PAYMENT DINNER TNG WALLET MEPS JOMPAY LP Interbank GIRO GLOBAL MONEY TRANSFER 10.00",
            ),
        ]

        report = render_review_report(rows, "outputs/statement.csv")

        self.assertIn("## Missing Amount Diagnostics", report)
        self.assertIn("| diagnostic=no amount candidates | 1 |", report)
        self.assertIn("| diagnostic=single amount candidate | 6 |", report)
        self.assertIn("| diagnostic=missing current balance | 1 |", report)
        self.assertIn("| diagnostic=missing previous balance | 1 |", report)
        self.assertIn("| diagnostic=non-numeric balance | 2 |", report)
        self.assertIn("| diagnostic=balance delta mismatch | 1 |", report)
        self.assertIn("| diagnostic=multiple transaction markers | 1 |", report)
        self.assertIn("missing amount, diagnostic=no amount candidates", report)
        self.assertIn("diagnostic=multiple transaction markers", report)
        self.assertNotIn("QR PAYMENT MISMATCH 10.00 900.00", report)
        self.assertNotIn("Interbank GIRO GLOBAL MONEY TRANSFER", report)

    def test_raw_text_is_not_rendered(self) -> None:
        row = _csv_row("SAFE DESCRIPTION", "4.00", "Other", "unknown", "review")
        row["raw_text"] = "SECRET RAW TEXT SHOULD NOT APPEAR"

        report = render_review_report([row], "outputs/statement.csv")

        self.assertIn("SAFE DESCRIPTION", report)
        self.assertNotIn("SECRET RAW TEXT SHOULD NOT APPEAR", report)
        self.assertNotIn("raw_text", report)

    def test_write_report_requires_outputs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_path = Path(tmp_dir) / "review-report.md"

            with self.assertRaises(ValueError):
                write_review_report([], "statement.csv", bad_path)

    def test_cli_requires_out_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "statement.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
                writer.writeheader()

            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    review_report_main([str(csv_path)])

        self.assertNotEqual(raised.exception.code, 0)

    def test_write_report_does_not_modify_input_csv_or_rules_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            csv_path = base / "statement.csv"
            rules_path = base / "rules.yml"
            out_path = base / "outputs" / "review-report.md"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerow(_csv_row("REPORT ROW", "5.00", "Other", "unknown", "review"))
            rules_text = "rules:\n  - pattern: \"X\"\n    category: \"Other\"\n    treatment: \"unknown\"\n"
            rules_path.write_text(rules_text, encoding="utf-8")
            original_csv = csv_path.read_text(encoding="utf-8")

            rows = read_report_csv(csv_path)
            write_review_report(rows, csv_path, out_path)

            self.assertTrue(out_path.exists())
            self.assertEqual(csv_path.read_text(encoding="utf-8"), original_csv)
            self.assertEqual(rules_path.read_text(encoding="utf-8"), rules_text)


class MonthlySummaryTests(unittest.TestCase):
    def test_groups_by_month_and_uses_treatment_semantics(self) -> None:
        rows = _monthly_rows()

        summaries, invalid_rows = build_monthly_summaries(rows)
        april = next(summary for summary in summaries if summary.month == "2026-04")
        may = next(summary for summary in summaries if summary.month == "2026-05")

        self.assertEqual(len(invalid_rows), 1)
        self.assertEqual(len(april.rows), 8)
        self.assertEqual(april.income_total, _decimal("5000.00"))
        self.assertEqual(april.transfer_in_total, _decimal("1000.00"))
        self.assertEqual(april.unknown_in_total, _decimal("200.00"))
        self.assertEqual(april.expense_total, _decimal("1250.50"))
        self.assertEqual(april.transfer_out_total, _decimal("300.00"))
        self.assertEqual(april.unknown_out_total, _decimal("25.00"))
        self.assertEqual(april.account_cashflow, _decimal("4624.50"))
        self.assertEqual(april.living_balance, _decimal("3749.50"))
        self.assertEqual(len(may.rows), 1)

    def test_rendered_report_contains_monthly_sections_warnings_and_no_raw_text(self) -> None:
        rows = _monthly_rows()
        rows[0]["raw_text"] = "SECRET RAW TEXT"

        report = render_monthly_summary(rows, "outputs/statement.csv")

        self.assertIn("# Bank Statement Monthly Summary", report)
        self.assertIn("Source CSV count: 1", report)
        self.assertIn("Source CSVs: statement.csv", report)
        self.assertIn("| 2026-04 | 8 | 2 | 4624.50 | 3749.50 | 5000.00 | 1250.50 | 1000.00 | 300.00 | 200.00 | 25.00 |", report)
        self.assertIn("## 2026-04", report)
        self.assertIn("| Dining | 3 | 0.00 | 1250.50 |", report)
        self.assertIn("| transfer | 2 | 1000.00 | 300.00 |", report)
        self.assertIn("- Review rows included in totals: 2", report)
        self.assertIn("- Unknown treatment rows included in account cashflow only: 2", report)
        self.assertIn("- Invalid or missing date rows excluded from month totals: 1", report)
        self.assertNotIn("SECRET RAW TEXT", report)
        self.assertNotIn("raw_text", report)

    def test_rendered_report_combines_multiple_csv_sources(self) -> None:
        bank_rows = [
            _monthly_row("2026-05-01", "SALARY", "5,000.00", "", "Income", "income", "auto"),
            _monthly_row("2026-05-02", "CARD PAYMENT", "", "1,000.00", "Transfer", "transfer", "auto"),
            _monthly_row("bad-date", "BAD DATE", "", "8.00", "Dining", "expense", "auto"),
        ]
        card_rows = [
            _monthly_row("2026-05-03", "CARD GROCERIES", "", "120.00", "Groceries", "expense", "auto"),
            _monthly_row("2026-05-04", "CARD UNKNOWN", "", "30.00", "Other", "unknown", "review"),
            _monthly_row("2026-05-05", "BROKERAGE REFUND", "200.00", "", "Transfer", "transfer", "auto"),
        ]

        report = render_monthly_summary(
            [*bank_rows, *card_rows],
            ["outputs/2026-05-06.statement.csv", "outputs/2026-05-21.card.statement.csv"],
        )

        self.assertIn("Source CSV count: 2", report)
        self.assertIn("Source CSVs: 2026-05-06.statement.csv, 2026-05-21.card.statement.csv", report)
        self.assertIn("| 2026-05 | 5 | 1 | 4050.00 | 4880.00 | 5000.00 | 120.00 | 200.00 | 1000.00 | 0.00 | 30.00 |", report)
        self.assertIn("| Groceries | 1 | 0.00 | 120.00 |", report)
        self.assertIn("| unknown | 1 | 0.00 | 30.00 |", report)
        self.assertIn("- Review rows included in totals: 1", report)
        self.assertIn("- Invalid or missing date rows excluded from month totals: 1", report)
        self.assertNotIn("RAW CARD GROCERIES", report)
        self.assertNotIn("raw_text", report)

    def test_top_expenses_sort_across_multiple_csv_sources(self) -> None:
        report = render_monthly_summary(
            [
                _monthly_row("2026-05-01", "BANK FOOD", "", "20.00", "Dining", "expense", "auto"),
                _monthly_row("2026-05-02", "CARD BIG SHOP", "", "200.00", "Shopping", "expense", "auto"),
            ],
            ["outputs/2026-05-06.statement.csv", "outputs/2026-05-21.card.statement.csv"],
        )

        self.assertLess(report.index("CARD BIG SHOP"), report.index("BANK FOOD"))

    def test_top_expenses_sort_by_money_out_and_exclude_transfers(self) -> None:
        report = render_monthly_summary(_monthly_rows(), "outputs/statement.csv")

        rent_position = report.index("RENT")
        groceries_position = report.index("GROCERIES")
        transfer_position = report.find("BROKERAGE OUT")

        self.assertLess(rent_position, groceries_position)
        self.assertEqual(transfer_position, -1)

    def test_top_expense_descriptions_are_cleaned_for_display_only(self) -> None:
        rows = [
            _monthly_row(
                "2026-04-01",
                "QR PAYMENT | HIB-123ABC | SEJIWA MEET & DINE PLT DWQR-20260408HBMBMYKL0300QR68743212 REF EB01-31858",
                "",
                "39.60",
                "Dining",
                "expense",
                "auto",
            ),
            _monthly_row(
                "2026-04-02",
                "VISA POS Shopee MY Marketplace REF A895-36492",
                "",
                "23.80",
                "Shopping",
                "expense",
                "auto",
            ),
        ]

        report = render_monthly_summary(rows, "outputs/statement.csv")

        self.assertIn("SEJIWA MEET & DINE PLT", report)
        self.assertIn("Shopee MY Marketplace", report)
        self.assertNotIn("QR PAYMENT", report)
        self.assertNotIn("HIB-123ABC", report)
        self.assertNotIn("DWQR-20260408HBMBMYKL0300QR68743212", report)
        self.assertNotIn("REF EB01-31858", report)
        self.assertEqual(
            rows[0]["description"],
            "QR PAYMENT | HIB-123ABC | SEJIWA MEET & DINE PLT DWQR-20260408HBMBMYKL0300QR68743212 REF EB01-31858",
        )

    def test_clean_description_removes_statement_artifacts(self) -> None:
        description = (
            "QR PAYMENT HIB-ABC Restoran Mazeela Bistro BALANCE CARRIEDFORWARD "
            "HSBC <x> Amanah 013562 Statement Details Re BALANCE BROUGHTFORWARD"
        )

        self.assertEqual(_clean_description_for_display(description), "Restoran Mazeela Bistro 013562 Re")

    def test_clean_description_removes_credit_card_artifacts_for_display_only(self) -> None:
        description = (
            "99 SPEEDMART-1096 _ SELANGOR _ MY 5 4617729026633785 "
            "goO00000000 OOO0000000 Amanah MPower Platinum Card-i cera number"
        )

        self.assertEqual(_clean_description_for_display(description), "99 SPEEDMART-1096 SELANGOR MY")

    def test_write_monthly_summary_requires_outputs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_path = Path(tmp_dir) / "monthly-summary.md"

            with self.assertRaises(ValueError):
                write_monthly_summary([], "statement.csv", bad_path)

    def test_write_monthly_summary_does_not_modify_input_csv_or_rules_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            csv_path = base / "statement.csv"
            rules_path = base / "rules.yml"
            out_path = base / "outputs" / "monthly-summary.md"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                for row in _monthly_rows():
                    writer.writerow(row)
            rules_text = "rules:\n  - pattern: \"X\"\n    category: \"Other\"\n    treatment: \"unknown\"\n"
            rules_path.write_text(rules_text, encoding="utf-8")
            original_csv = csv_path.read_text(encoding="utf-8")

            rows = read_monthly_csv(csv_path)
            write_monthly_summary(rows, csv_path, out_path)

            self.assertTrue(out_path.exists())
            self.assertEqual(csv_path.read_text(encoding="utf-8"), original_csv)
            self.assertEqual(rules_path.read_text(encoding="utf-8"), rules_text)

    def test_reads_multiple_statement_csvs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            first_path = base / "first.csv"
            second_path = base / "second.csv"
            for path, row in [
                (first_path, _monthly_row("2026-05-01", "FIRST", "1.00", "", "Income", "income", "auto")),
                (second_path, _monthly_row("2026-05-02", "SECOND", "", "2.00", "Dining", "expense", "auto")),
            ]:
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
                    writer.writeheader()
                    writer.writerow(row)

            rows = read_monthly_csvs([first_path, second_path])

            self.assertEqual([row["description"] for row in rows], ["FIRST", "SECOND"])

    def test_monthly_summary_cli_accepts_multiple_csv_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            first_path = base / "2026-05-06.statement.csv"
            second_path = base / "2026-05-21.card.statement.csv"
            out_path = base / "outputs" / "2026-05.combined.summary.md"
            for path, row in [
                (first_path, _monthly_row("2026-05-01", "FIRST", "1.00", "", "Income", "income", "auto")),
                (second_path, _monthly_row("2026-05-02", "SECOND", "", "2.00", "Dining", "expense", "auto")),
            ]:
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
                    writer.writeheader()
                    writer.writerow(row)

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = monthly_summary_main([str(first_path), str(second_path), "--out", str(out_path)])

            self.assertEqual(exit_code, 0)
            report = out_path.read_text(encoding="utf-8")
            self.assertIn("Source CSV count: 2", report)
            self.assertIn("Source CSVs: 2026-05-06.statement.csv, 2026-05-21.card.statement.csv", report)


def _csv_row(
    description: str,
    money_out: str,
    category: str,
    treatment: str,
    status: str,
    money_in: str = "",
) -> dict[str, str]:
    return {
        "date": "2026-05-01",
        "description": description,
        "money_in": money_in,
        "money_out": money_out,
        "balance": "100.00",
        "category": category,
        "treatment": treatment,
        "status": status,
        "raw_text": description,
    }


def _review_diagnostic_row(
    description: str,
    balance: str,
    raw_text: str,
    money_out: str = "",
    money_in: str = "",
) -> dict[str, str]:
    return {
        "date": "2026-05-01",
        "description": description,
        "money_in": money_in,
        "money_out": money_out,
        "balance": balance,
        "category": "Dining",
        "treatment": "expense",
        "status": "auto",
        "raw_text": raw_text,
    }


def _monthly_rows() -> list[dict[str, str]]:
    return [
        _monthly_row("2026-04-01", "SALARY", "5,000.00", "", "Income", "income", "auto"),
        _monthly_row("2026-04-02", "BROKERAGE IN", "1,000.00", "", "Transfer", "transfer", "auto"),
        _monthly_row("2026-04-03", "UNKNOWN IN", "200.00", "", "Other", "unknown", "review"),
        _monthly_row("2026-04-04", "RENT", "", "1,200.50", "Dining", "expense", "auto"),
        _monthly_row("2026-04-05", "GROCERIES", "", "50.00", "Dining", "expense", "auto"),
        _monthly_row("2026-04-06", "BROKERAGE OUT", "", "300.00", "Transfer", "transfer", "auto"),
        _monthly_row("2026-04-07", "UNKNOWN OUT", "", "25.00", "Other", "unknown", "review"),
        _monthly_row("2026-04-08", "MISSING AMOUNT", "", "", "Dining", "expense", "auto"),
        _monthly_row("2026-05-01", "MAY FOOD", "", "10.00", "Dining", "expense", "auto"),
        _monthly_row("not-a-date", "BAD DATE", "", "99.00", "Dining", "expense", "auto"),
    ]


def _monthly_row(
    date: str,
    description: str,
    money_in: str,
    money_out: str,
    category: str,
    treatment: str,
    status: str,
) -> dict[str, str]:
    return {
        "date": date,
        "description": description,
        "money_in": money_in,
        "money_out": money_out,
        "balance": "100.00",
        "category": category,
        "treatment": treatment,
        "status": status,
        "raw_text": f"RAW {description}",
    }


def _decimal(value: str):
    from decimal import Decimal

    return Decimal(value)


if __name__ == "__main__":
    unittest.main()
