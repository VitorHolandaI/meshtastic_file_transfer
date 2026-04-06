"""
Layer 2 — Protocol logic: receiver state machine (receiver.py)
Uses unittest.mock to replace mesh_interface. No hardware required.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import receiver
from meshtcp import make_header, make_chunk, make_ack, make_abort, make_done

RESET_STATE = {
    "active": False,
    "filename": None,
    "total_chunks": 0,
    "md5_hash": None,
    "chunks": {},
    "complete": False,
}


def make_packet(payload):
    return {"fromId": "!aabbccdd", "decoded": {"payload": payload}}


def sent_payloads(mock_iface):
    """Return list of data payloads passed to sendData calls."""
    return [c[0][0] for c in mock_iface.sendData.call_args_list]


class TestReceiverFilePacket(unittest.TestCase):

    def setUp(self):
        receiver.transfer.update(RESET_STATE.copy())
        receiver.transfer["chunks"] = {}
        receiver.mesh_interface = Mock()

    @patch("receiver.time.sleep")
    def test_file_sets_transfer_active(self, _sleep):
        receiver.on_receive(make_packet(make_header("a.txt", 5, "md5abc")), None)
        self.assertTrue(receiver.transfer["active"])

    @patch("receiver.time.sleep")
    def test_file_stores_metadata(self, _sleep):
        receiver.on_receive(make_packet(make_header("img.png", 10, "deadbeef")), None)
        self.assertEqual(receiver.transfer["filename"], "img.png")
        self.assertEqual(receiver.transfer["total_chunks"], 10)
        self.assertEqual(receiver.transfer["md5_hash"], "deadbeef")

    @patch("receiver.time.sleep")
    def test_file_resets_chunks_and_complete(self, _sleep):
        receiver.transfer["chunks"] = {1: b"old"}
        receiver.transfer["complete"] = True
        receiver.on_receive(make_packet(make_header("new.txt", 2, "abc")), None)
        self.assertEqual(receiver.transfer["chunks"], {})
        self.assertFalse(receiver.transfer["complete"])


class TestReceiverChkPacket(unittest.TestCase):

    def setUp(self):
        receiver.transfer.update(RESET_STATE.copy())
        receiver.transfer["chunks"] = {}
        receiver.transfer["active"] = True
        receiver.transfer["total_chunks"] = 3
        receiver.mesh_interface = Mock()

    @patch("receiver.time.sleep")
    def test_chk_stores_chunk(self, _sleep):
        receiver.on_receive(make_packet(make_chunk(1, b"data")), None)
        self.assertEqual(receiver.transfer["chunks"][1], b"data")

    @patch("receiver.time.sleep")
    def test_chk_sends_ack_three_times(self, _sleep):
        receiver.on_receive(make_packet(make_chunk(2, b"data")), None)
        payloads = sent_payloads(receiver.mesh_interface)
        self.assertEqual(len(payloads), 3)
        for p in payloads:
            self.assertEqual(p, make_ack(2))

    @patch("receiver.time.sleep")
    def test_chk_ack_sleeps_between_sends(self, mock_sleep):
        receiver.on_receive(make_packet(make_chunk(1, b"x")), None)
        # 2 sleeps of 1.5s between 3 ACKs
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        self.assertEqual(sleep_calls.count(1.5), 2)

    @patch("receiver.time.sleep")
    def test_chk_duplicate_does_not_double_count(self, _sleep):
        receiver.on_receive(make_packet(make_chunk(1, b"first")), None)
        receiver.mesh_interface.sendData.reset_mock()
        receiver.on_receive(make_packet(make_chunk(1, b"second")), None)
        # chunk still overwritten but count stays 1
        self.assertEqual(len(receiver.transfer["chunks"]), 1)
        # ACK still sent 3 times for duplicate
        self.assertEqual(receiver.mesh_interface.sendData.call_count, 3)

    @patch("receiver.time.sleep")
    def test_chk_ignored_when_not_active(self, _sleep):
        receiver.transfer["active"] = False
        receiver.on_receive(make_packet(make_chunk(1, b"data")), None)
        self.assertEqual(receiver.transfer["chunks"], {})
        receiver.mesh_interface.sendData.assert_not_called()

    @patch("receiver.save_file")
    @patch("receiver.time.sleep")
    def test_all_chunks_triggers_save_file(self, _sleep, mock_save):
        receiver.transfer["total_chunks"] = 2
        receiver.on_receive(make_packet(make_chunk(1, b"a")), None)
        receiver.on_receive(make_packet(make_chunk(2, b"b")), None)
        mock_save.assert_called_once()

    @patch("receiver.save_file")
    @patch("receiver.time.sleep")
    def test_all_chunks_sets_inactive(self, _sleep, _save):
        receiver.transfer["total_chunks"] = 1
        receiver.on_receive(make_packet(make_chunk(1, b"a")), None)
        self.assertFalse(receiver.transfer["active"])

    @patch("receiver.save_file")
    @patch("receiver.time.sleep")
    def test_complete_flag_prevents_double_save(self, _sleep, mock_save):
        receiver.transfer["total_chunks"] = 1
        receiver.on_receive(make_packet(make_chunk(1, b"a")), None)
        receiver.transfer["active"] = True  # force re-active
        receiver.transfer["complete"] = True
        receiver.on_receive(make_packet(make_chunk(1, b"a")), None)
        mock_save.assert_called_once()  # not twice


class TestReceiverAbort(unittest.TestCase):

    def setUp(self):
        receiver.transfer.update(RESET_STATE.copy())
        receiver.transfer["chunks"] = {1: b"data"}
        receiver.transfer["active"] = True
        receiver.mesh_interface = Mock()

    @patch("receiver.time.sleep")
    def test_abort_clears_active(self, _sleep):
        receiver.on_receive(make_packet(make_abort()), None)
        self.assertFalse(receiver.transfer["active"])

    @patch("receiver.time.sleep")
    def test_abort_clears_chunks(self, _sleep):
        receiver.on_receive(make_packet(make_abort()), None)
        self.assertEqual(receiver.transfer["chunks"], {})


class TestReceiverMalformedPackets(unittest.TestCase):

    def setUp(self):
        receiver.transfer.update(RESET_STATE.copy())
        receiver.transfer["chunks"] = {}
        receiver.mesh_interface = Mock()

    def test_no_decoded_key_ignored(self):
        receiver.on_receive({"fromId": "!abc"}, None)
        receiver.mesh_interface.sendData.assert_not_called()

    def test_no_payload_key_ignored(self):
        receiver.on_receive({"decoded": {}}, None)
        receiver.mesh_interface.sendData.assert_not_called()

    def test_non_bytes_payload_ignored(self):
        receiver.on_receive({"decoded": {"payload": "string not bytes"}}, None)
        receiver.mesh_interface.sendData.assert_not_called()


if __name__ == "__main__":
    unittest.main()
