"""Tests for the cato-sdp output parser. Run: python3 -m unittest discover tests"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sdp_shield import NOT_FOUND_MSG, human_bytes, parse_status  # noqa: E402

CONNECTED = """Cato Client: 5.8.1.1234
pop id      = 1
pop name    = "example-pop"
pop address = 192.0.2.10
tunnel ip   = 10.0.0.2
dns1        = 10.0.0.53
dns2        = 192.0.2.53
tun device  = tun0
duration             = 01:02:03
bio_rx_bytes         = 2048 (2.0Kb)
bio_tx_bytes         = 1024 (1.0Kb)
rx_packets           = 20
tx_packets           = 10
rtt                  = 50/10/14/40/12 (n/min/avg/max/last)
last_read_sec        = 00:00:00
state                = STATE_AUTHENTICATED
connected_via_office = no
------------------------------------
Account: example-account
User: user@example.com
"""


class ParseStatus(unittest.TestCase):
    def test_disconnected(self):
        s = parse_status(True, "Cato client is disconnected")
        self.assertFalse(s.connected)
        self.assertFalse(s.connecting)
        self.assertTrue(s.daemon_ok)

    def test_connected_block(self):
        s = parse_status(True, CONNECTED)
        self.assertTrue(s.connected)
        self.assertEqual(s.client_version, "5.8.1.1234")
        self.assertEqual(s.duration, "01:02:03")
        self.assertEqual(s.pop, "example-pop")
        self.assertEqual(s.get("tunnel ip"), "10.0.0.2")
        self.assertEqual(s.bytes("bio_rx_bytes"), 2048)
        self.assertEqual(s.rtt, (14, 12))
        self.assertEqual(s.user, "user@example.com")
        self.assertEqual(s.account, "example-account")
        start = s.session_start
        self.assertEqual(s.when - start, dt.timedelta(hours=1, minutes=2, seconds=3))

    def test_connecting(self):
        self.assertTrue(parse_status(True, "state = STATE_CONNECTED_UNAUTH").connecting)
        self.assertTrue(parse_status(False, "Failed to deserialize cmd").connecting)

    def test_daemon_down(self):
        s = parse_status(False, "Failed to connect to Cato client daemon")
        self.assertFalse(s.daemon_ok)

    def test_not_installed(self):
        self.assertFalse(parse_status(False, NOT_FOUND_MSG).daemon_ok)

    def test_human_bytes(self):
        self.assertEqual(human_bytes(0), "0 Bytes")
        self.assertEqual(human_bytes(1536), "1.5 KB")
        self.assertEqual(human_bytes(None), "N/A")


if __name__ == "__main__":
    unittest.main()
