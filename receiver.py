"""
MeshTCP Receiver - Reliable file transfer over Meshtastic
Receives chunks, sends ACK for each, verifies MD5 at the end.
"""

import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import sys
import time
import os
import signal
import glob

from meshtcp import (
    PORT_NUM, HOP_LIMIT,
    make_ack, make_nack, make_done, make_abort,
    parse_packet, bytes_md5, disable_pkc,
)

OUTPUT_DIR = "received_files"
SENDER_ID = 3382279048  # 7b88 (V2.1) on ttyUSB1

# Transfer state
transfer = {
    "active": False,
    "filename": None,
    "total_chunks": 0,
    "md5_hash": None,
    "chunks": {},
    "complete": False,
}

mesh_interface = None


def cleanup(sig, frame):
    print("\nStopping...")
    if mesh_interface:
        mesh_interface.close()
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)


def send_packet(data):
    mesh_interface.sendData(
        data,
        destinationId=SENDER_ID,
        portNum=PORT_NUM,
        hopLimit=HOP_LIMIT,
        wantAck=False,
    )


def save_file():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    data = b""
    for i in range(1, transfer["total_chunks"] + 1):
        if i in transfer["chunks"]:
            data += transfer["chunks"][i]
        else:
            print(f"  !! Missing chunk {i}")

    filepath = os.path.join(OUTPUT_DIR, transfer["filename"])
    with open(filepath, "wb") as f:
        f.write(data)

    print(f"\n  File saved: {os.path.abspath(filepath)} ({len(data)} bytes)")

    received_md5 = bytes_md5(data)
    expected_md5 = transfer["md5_hash"]

    print(f"  Expected MD5: {expected_md5}")
    print(f"  Received MD5: {received_md5}")

    md5_ok = received_md5 == expected_md5

    if md5_ok:
        print("  MD5 MATCH! File is intact.")
    else:
        print("  MD5 MISMATCH! File is corrupted.")

    for repeat in range(1, 4):
        send_packet(make_done(md5_ok))
        print(f"  -> DONE sent ({'md5_ok' if md5_ok else 'md5_fail'}) [{repeat}/3]")
        if repeat < 3:
            time.sleep(2)

    return md5_ok


def on_receive(packet, interface):
    from_id = packet.get("fromId", "")

    if "decoded" not in packet:
        return

    decoded = packet["decoded"]
    if "payload" not in decoded:
        return

    raw = decoded["payload"]
    if not isinstance(raw, bytes):
        return

    ptype, fields = parse_packet(raw)

    if ptype == "FILE":
        transfer["active"] = True
        transfer["filename"] = fields["filename"]
        transfer["total_chunks"] = fields["total_chunks"]
        transfer["md5_hash"] = fields["md5_hash"]
        transfer["chunks"] = {}
        transfer["complete"] = False

        print(f"\n{'='*50}")
        print(f"  Incoming file: {fields['filename']}")
        print(f"  Chunks: {fields['total_chunks']}")
        print(f"  MD5: {fields['md5_hash']}")
        print(f"{'='*50}")

    elif ptype == "CHK":
        if not transfer["active"]:
            return

        chunk_num = fields["chunk_num"]
        chunk_data = fields["data"]

        is_new = chunk_num not in transfer["chunks"]
        transfer["chunks"][chunk_num] = chunk_data

        received = len(transfer["chunks"])
        total = transfer["total_chunks"]

        if is_new:
            print(f"  <- CHK {chunk_num}/{total} ({len(chunk_data)}B) [{received}/{total}]")
        else:
            print(f"  <- CHK {chunk_num}/{total} (duplicate, re-ACKing)")

        for repeat in range(1, 4):
            send_packet(make_ack(chunk_num))
            print(f"  -> ACK {chunk_num} [{repeat}/3]")
            if repeat < 3:
                time.sleep(1.5)

        if received == total and not transfer["complete"]:
            transfer["complete"] = True
            print(f"\n  All {total} chunks received! Verifying...")
            time.sleep(1)
            save_file()
            transfer["active"] = False

    elif ptype == "ABORT":
        print("\n  <- ABORT from sender. Transfer cancelled.")
        transfer["active"] = False
        transfer["chunks"] = {}


def find_port():
    ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    return ports[0] if ports else None


def connect(retry_interval=5, max_wait=120):
    """Find any available serial device and connect, retrying until it enumerates."""
    deadline = time.time() + max_wait
    while True:
        port = find_port()
        if not port:
            remaining = int(deadline - time.time())
            if remaining <= 0:
                print(f"  !! Device did not re-enumerate after {max_wait}s. Give up.")
                sys.exit(1)
            print(f"  Waiting for device to appear... ({remaining}s left)")
            time.sleep(retry_interval)
            continue
        try:
            print(f"  Connecting to {port}...")
            iface = meshtastic.serial_interface.SerialInterface(port)
            time.sleep(2)
            return iface
        except Exception as e:
            remaining = int(deadline - time.time())
            if remaining <= 0:
                print(f"  !! Could not connect after {max_wait}s: {e}")
                sys.exit(1)
            print(f"  Connect failed ({port}): {e}. Retrying in {retry_interval}s... ({remaining}s left)")
            time.sleep(retry_interval)


def main():
    global mesh_interface

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    pub.subscribe(on_receive, "meshtastic.receive")

    mesh_interface = connect()

    disable_pkc(mesh_interface)

    my_node = mesh_interface.myInfo.my_node_num
    print(f"Connected! Node: {my_node}")
    print(f"Saving files to: {os.path.abspath(OUTPUT_DIR)}/")
    print("Waiting for file transfer... Press Ctrl+C to stop.\n")

    while True:
        try:
            time.sleep(1)
        except Exception:
            print("\n  !! Serial connection lost. Reconnecting...")
            try:
                mesh_interface.close()
            except Exception:
                pass
            time.sleep(10)  # wait longer — cp210x needs time after power cycle
            mesh_interface = connect(retry_interval=5, max_wait=120)
            disable_pkc(mesh_interface)
            print(f"  Reconnected! Node: {mesh_interface.myInfo.my_node_num}")
            print("  Waiting for file transfer...\n")


if __name__ == "__main__":
    main()
