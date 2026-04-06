"""
Layer 2 — Protocol logic: sender event handler (sender.py)
Tests on_receive: ACK/NAK/DONE/ABORT correctly update globals and fire ack_event.
No hardware, no threading, no file I/O.
"""

import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sender
from meshtcp import make_ack, make_nack, make_done, make_abort


def make_packet(payload):
    return {"fromId": "!aabbccdd", "decoded": {"payload": payload}}


class TestSenderOnReceive(unittest.TestCase):

    def setUp(self):
        sender.ack_received_num = -1
        sender.transfer_aborted = False
        sender.transfer_done = False
        sender.ack_event.clear()

    # --- ACK ---

    def test_ack_sets_chunk_num(self):
        sender.on_receive(make_packet(make_ack(4)), None)
        self.assertEqual(sender.ack_received_num, 4)

    def test_ack_fires_event(self):
        sender.on_receive(make_packet(make_ack(1)), None)
        self.assertTrue(sender.ack_event.is_set())

    def test_ack_does_not_set_aborted(self):
        sender.on_receive(make_packet(make_ack(1)), None)
        self.assertFalse(sender.transfer_aborted)

    # --- NAK ---

    def test_nak_fires_event(self):
        sender.on_receive(make_packet(make_nack(2)), None)
        self.assertTrue(sender.ack_event.is_set())

    def test_nak_does_not_set_chunk_num(self):
        sender.on_receive(make_packet(make_nack(2)), None)
        self.assertEqual(sender.ack_received_num, -1)

    # --- DONE md5_ok ---

    def test_done_ok_sets_transfer_done(self):
        sender.on_receive(make_packet(make_done(True)), None)
        self.assertTrue(sender.transfer_done)

    def test_done_ok_fires_event(self):
        sender.on_receive(make_packet(make_done(True)), None)
        self.assertTrue(sender.ack_event.is_set())

    def test_done_ok_does_not_abort(self):
        sender.on_receive(make_packet(make_done(True)), None)
        self.assertFalse(sender.transfer_aborted)

    # --- DONE md5_fail ---

    def test_done_fail_sets_aborted(self):
        sender.on_receive(make_packet(make_done(False)), None)
        self.assertTrue(sender.transfer_aborted)

    def test_done_fail_fires_event(self):
        sender.on_receive(make_packet(make_done(False)), None)
        self.assertTrue(sender.ack_event.is_set())

    def test_done_fail_does_not_set_transfer_done(self):
        sender.on_receive(make_packet(make_done(False)), None)
        self.assertFalse(sender.transfer_done)

    # --- ABORT ---

    def test_abort_sets_aborted(self):
        sender.on_receive(make_packet(make_abort()), None)
        self.assertTrue(sender.transfer_aborted)

    def test_abort_fires_event(self):
        sender.on_receive(make_packet(make_abort()), None)
        self.assertTrue(sender.ack_event.is_set())

    # --- malformed ---

    def test_no_decoded_ignored(self):
        sender.on_receive({"fromId": "!abc"}, None)
        self.assertFalse(sender.ack_event.is_set())
        self.assertEqual(sender.ack_received_num, -1)

    def test_no_payload_ignored(self):
        sender.on_receive({"decoded": {}}, None)
        self.assertFalse(sender.ack_event.is_set())

    def test_unknown_payload_ignored(self):
        sender.on_receive(make_packet(b"GARBAGE"), None)
        self.assertFalse(sender.ack_event.is_set())
        self.assertFalse(sender.transfer_aborted)
        self.assertFalse(sender.transfer_done)


if __name__ == "__main__":
    unittest.main()
