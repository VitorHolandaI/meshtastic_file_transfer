"""
Layer 1 — Unit tests: protocol serialization (meshtcp.py)
No hardware, no mocks, no network.
"""

import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from meshtcp import (
    MAX_CHUNK_DATA,
    MAX_PAYLOAD,
    make_ack,
    make_abort,
    make_chunk,
    make_done,
    make_header,
    make_nack,
    parse_packet,
    bytes_md5,
    file_md5,
)


class TestMakeAndParse(unittest.TestCase):

    def test_header_roundtrip(self):
        pkt = make_header("foto.jpg", 42, "abc123")
        ptype, fields = parse_packet(pkt)
        self.assertEqual(ptype, "FILE")
        self.assertEqual(fields["filename"], "foto.jpg")
        self.assertEqual(fields["total_chunks"], 42)
        self.assertEqual(fields["md5_hash"], "abc123")

    def test_chunk_roundtrip_text(self):
        data = b"hello world"
        pkt = make_chunk(7, data)
        ptype, fields = parse_packet(pkt)
        self.assertEqual(ptype, "CHK")
        self.assertEqual(fields["chunk_num"], 7)
        self.assertEqual(fields["data"], data)

    def test_chunk_roundtrip_binary(self):
        # Binary data with pipe bytes (|) must not confuse the parser
        data = bytes(range(256))
        pkt = make_chunk(1, data)
        ptype, fields = parse_packet(pkt)
        self.assertEqual(ptype, "CHK")
        self.assertEqual(fields["data"], data)

    def test_chunk_roundtrip_empty_data(self):
        pkt = make_chunk(3, b"")
        ptype, fields = parse_packet(pkt)
        self.assertEqual(ptype, "CHK")
        self.assertEqual(fields["chunk_num"], 3)
        self.assertEqual(fields["data"], b"")

    def test_ack_roundtrip(self):
        pkt = make_ack(5)
        ptype, fields = parse_packet(pkt)
        self.assertEqual(ptype, "ACK")
        self.assertEqual(fields["chunk_num"], 5)

    def test_nack_roundtrip(self):
        pkt = make_nack(9)
        ptype, fields = parse_packet(pkt)
        self.assertEqual(ptype, "NAK")
        self.assertEqual(fields["chunk_num"], 9)

    def test_done_md5_ok(self):
        pkt = make_done(True)
        ptype, fields = parse_packet(pkt)
        self.assertEqual(ptype, "DONE")
        self.assertEqual(fields["status"], "md5_ok")

    def test_done_md5_fail(self):
        pkt = make_done(False)
        ptype, fields = parse_packet(pkt)
        self.assertEqual(ptype, "DONE")
        self.assertEqual(fields["status"], "md5_fail")

    def test_abort(self):
        pkt = make_abort()
        ptype, fields = parse_packet(pkt)
        self.assertEqual(ptype, "ABORT")
        self.assertEqual(fields, {})

    def test_parse_string_input(self):
        # parse_packet must accept str and auto-encode
        ptype, fields = parse_packet("ACK|3")
        self.assertEqual(ptype, "ACK")
        self.assertEqual(fields["chunk_num"], 3)

    def test_parse_garbage_returns_unknown(self):
        ptype, fields = parse_packet(b"NOTAPACKET")
        self.assertEqual(ptype, "UNKNOWN")

    def test_parse_empty_returns_unknown(self):
        ptype, fields = parse_packet(b"")
        self.assertEqual(ptype, "UNKNOWN")


class TestPacketSize(unittest.TestCase):

    def test_max_chunk_fits_in_payload(self):
        data = b"x" * MAX_CHUNK_DATA
        pkt = make_chunk(9999, data)
        self.assertLessEqual(
            len(pkt),
            MAX_PAYLOAD,
            f"Chunk packet {len(pkt)}B exceeds MAX_PAYLOAD {MAX_PAYLOAD}B",
        )

    def test_header_fits_in_payload(self):
        long_name = "a" * 64
        md5 = "f" * 32
        pkt = make_header(long_name, 9999, md5)
        self.assertLessEqual(len(pkt), MAX_PAYLOAD)


class TestMd5(unittest.TestCase):

    def test_bytes_md5_known_value(self):
        result = bytes_md5(b"")
        self.assertEqual(result, "d41d8cd98f00b204e9800998ecf8427e")

    def test_bytes_md5_known_string(self):
        result = bytes_md5(b"meshtastic")
        expected = hashlib.md5(b"meshtastic").hexdigest()
        self.assertEqual(result, expected)

    def test_file_md5_matches_bytes_md5(self):
        content = b"test file content 1234"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            path = f.name
        try:
            self.assertEqual(file_md5(path), bytes_md5(content))
        finally:
            os.unlink(path)

    def test_file_md5_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            self.assertEqual(file_md5(path), bytes_md5(b""))
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
