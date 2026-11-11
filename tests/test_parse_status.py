"""Tests for the cato-sdp output parser. Run: python3 -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sdp_shield import NOT_FOUND_MSG, parse_status  # noqa: E402


class ParseStatus(unittest.TestCase):
    def test_disconnected(self):
        s = parse_status(True, "Cato client is disconnected")
        self.assertFalse(s.connected)
        self.assertFalse(s.connecting)
        self.assertTrue(s.daemon_ok)

    def test_connected_block(self):
        raw = ("state = STATE_AUTHENTICATED\n"
               "duration = 00:12:34\n"
               "account = example-account\n"
               "pop name = Example PoP\n"
               "tunnel ip = 10.0.0.2\n")
        s = parse_status(True, raw)
        self.assertTrue(s.connected)
        self.assertEqual(s.uptime, "00:12:34")
        self.assertEqual(s.account, "Account: example-account")
        self.assertEqual(s.pop, "Example PoP  ·  10.0.0.2")

    def test_connecting(self):
        self.assertTrue(parse_status(True, "state = STATE_CONNECTED_UNAUTH").connecting)
        self.assertTrue(parse_status(False, "Failed to deserialize cmd").connecting)

    def test_daemon_down(self):
        s = parse_status(False, "Failed to connect to Cato client daemon")
        self.assertFalse(s.daemon_ok)

    def test_not_installed(self):
        self.assertFalse(parse_status(False, NOT_FOUND_MSG).daemon_ok)


if __name__ == "__main__":
    unittest.main()
