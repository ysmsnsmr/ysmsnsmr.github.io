#!/usr/bin/env python3
import unittest
from unittest.mock import patch

import malaysia_rss_summary as summary


class FetchRssRetryTest(unittest.TestCase):
    def test_retries_transient_name_resolution_failure(self) -> None:
        dns_failure = summary.FetchResult(
            ok=False,
            url="https://www.businesstoday.com.my/feed/",
            method="curl",
            error="curl exit 6: Could not resolve host: www.businesstoday.com.my",
        )
        success = summary.FetchResult(
            ok=True,
            url="https://www.businesstoday.com.my/feed/",
            data=b"<rss />",
            status="200",
            content_type="application/rss+xml",
            method="urllib",
        )
        urllib_results = [dns_failure, dns_failure, success]
        curl_results = [dns_failure, dns_failure]

        with patch.object(summary, "fetch_urllib", side_effect=urllib_results) as urllib_mock, patch.object(
            summary, "fetch_curl", side_effect=curl_results
        ) as curl_mock, patch.object(summary.time, "sleep") as sleep_mock:
            result = summary.fetch_rss("https://www.businesstoday.com.my/feed/")

        self.assertTrue(result.ok)
        self.assertEqual(urllib_mock.call_count, 3)
        self.assertEqual(curl_mock.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in sleep_mock.call_args_list],
            [summary.DNS_RETRY_BACKOFF_SECONDS, summary.DNS_RETRY_BACKOFF_SECONDS * 2],
        )

    def test_does_not_retry_non_name_resolution_failure(self) -> None:
        urllib_failure = summary.FetchResult(
            ok=False,
            url="https://example.test/feed/",
            method="urllib",
            error="TimeoutError: request timed out",
        )
        curl_failure = summary.FetchResult(
            ok=False,
            url="https://example.test/feed/",
            method="curl",
            error="curl exit 28: operation timed out",
        )

        with patch.object(summary, "fetch_urllib", return_value=urllib_failure) as urllib_mock, patch.object(
            summary, "fetch_curl", return_value=curl_failure
        ) as curl_mock, patch.object(summary.time, "sleep") as sleep_mock:
            result = summary.fetch_rss("https://example.test/feed/")

        self.assertFalse(result.ok)
        self.assertEqual(urllib_mock.call_count, 1)
        self.assertEqual(curl_mock.call_count, 1)
        sleep_mock.assert_not_called()
        self.assertIn("urllib failed:", result.error)
        self.assertIn("curl failed:", result.error)


if __name__ == "__main__":
    unittest.main()
