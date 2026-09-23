#!/usr/bin/env python3
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.request import Request

from jev_shadow_transport import JevRequestError, _NoRedirectHandler, post_jev_request


class _RedirectBlockedOpener:
    def open(self, _request: Request, timeout: float) -> object:
        del timeout
        raise JevRequestError("redirect_blocked")


class JevTransportTests(unittest.TestCase):
    def test_redirect_handler_rejects_all_standard_redirect_statuses(self) -> None:
        handler = _NoRedirectHandler()
        request = Request(
            "https://api.typesafe.ai/v1/systemone",
            data=b"{}",
            headers={"Authorization": "Bearer fixture-key"},
            method="POST",
        )
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status), self.assertRaisesRegex(JevRequestError, "redirect_blocked"):
                handler.redirect_request(
                    request,
                    None,
                    status,
                    "redirect",
                    Message(),
                    "https://example.invalid/redirect",
                )

    def test_transport_uses_no_proxy_and_preserves_redirect_blocked(self) -> None:
        opener = _RedirectBlockedOpener()
        with patch("jev_shadow_transport.urllib.request.build_opener", return_value=opener) as build_opener:
            with self.assertRaisesRegex(JevRequestError, "redirect_blocked") as error:
                post_jev_request({"fixture": True}, "fixture-key", 1.0)

        self.assertEqual(error.exception.code, "redirect_blocked")
        handlers = build_opener.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], _NoRedirectHandler)


if __name__ == "__main__":
    unittest.main()
