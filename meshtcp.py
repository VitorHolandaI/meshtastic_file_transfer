"""
MeshTCP - Reliable file transfer over Meshtastic
Protocol shared between sender and receiver.

Packet format (all sent as bytes via sendData portNum=256):
  HEADER:  b"FILE|filename|total_chunks|md5_hash"
  CHUNK:   b"CHK|chunk_number|data..."
  ACK:     b"ACK|chunk_number"
  NACK:    b"NAK|chunk_number"         (request retransmit)
  DONE:    b"DONE|md5_ok"  or  b"DONE|md5_fail"
  ABORT:   b"ABORT"

Max meshtastic payload: 228 bytes
Usable data per chunk: 200 bytes (conservative)
"""

import hashlib
import time

PORT_NUM = 256  # PRIVATE_APP
MAX_PAYLOAD = 228
MAX_CHUNK_DATA = 200
HOP_LIMIT = 3
ACK_TIMEOUT = 15
MAX_RETRIES = 5
SEPARATOR = b"|"


def disable_pkc(interface):
    """Disable PKC encryption so packets arrive decoded, not encrypted.
    Call this right after creating the SerialInterface."""
    try:
        node = interface.getNode("^local")
        security = node.localConfig.security

        if security.public_key or security.private_key:
            print("  Disabling PKC encryption...")
            security.public_key = b""
            security.private_key = b""
            node.writeConfig("security")
            time.sleep(2)
            print("  PKC disabled.")
        else:
            print("  PKC already disabled.")
    except Exception as e:
        print(f"  Warning: could not disable PKC: {e}")


def make_header(filename, total_chunks, md5_hash):
    return f"FILE|{filename}|{total_chunks}|{md5_hash}".encode("utf-8")


def make_chunk(chunk_num, data):
    header = f"CHK|{chunk_num}|".encode("utf-8")
    return header + data


def make_ack(chunk_num):
    return f"ACK|{chunk_num}".encode("utf-8")


def make_nack(chunk_num):
    return f"NAK|{chunk_num}".encode("utf-8")


def make_done(md5_ok):
    status = "md5_ok" if md5_ok else "md5_fail"
    return f"DONE|{status}".encode("utf-8")


def make_abort():
    return b"ABORT"


def parse_packet(raw_bytes):
    if isinstance(raw_bytes, str):
        raw_bytes = raw_bytes.encode("utf-8")

    if raw_bytes.startswith(b"CHK|"):
        first = raw_bytes.index(b"|")
        second = raw_bytes.index(b"|", first + 1)
        chunk_num = int(raw_bytes[first + 1 : second])
        data = raw_bytes[second + 1 :]
        return ("CHK", {"chunk_num": chunk_num, "data": data})

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return ("UNKNOWN", {})

    parts = text.split("|")

    if parts[0] == "FILE" and len(parts) == 4:
        return ("FILE", {
            "filename": parts[1],
            "total_chunks": int(parts[2]),
            "md5_hash": parts[3],
        })

    if parts[0] == "ACK" and len(parts) == 2:
        return ("ACK", {"chunk_num": int(parts[1])})

    if parts[0] == "NAK" and len(parts) == 2:
        return ("NAK", {"chunk_num": int(parts[1])})

    if parts[0] == "DONE" and len(parts) == 2:
        return ("DONE", {"status": parts[1]})

    if parts[0] == "ABORT":
        return ("ABORT", {})

    return ("UNKNOWN", {})


def file_md5(filepath):
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            h.update(block)
    return h.hexdigest()


def bytes_md5(data):
    return hashlib.md5(data).hexdigest()
