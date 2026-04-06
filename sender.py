"""
MeshTCP Sender - Reliable file transfer over Meshtastic
Sends a file chunk by chunk, waits for ACK on each, retransmits on timeout.
"""

import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import sys
import time
import os
import threading
import glob

from meshtcp import (
    PORT_NUM, HOP_LIMIT, MAX_CHUNK_DATA, ACK_TIMEOUT, MAX_RETRIES,
    make_header, make_chunk, make_done, make_abort,
    parse_packet, file_md5, disable_pkc,
)

DEST_ID = 2896785728  # 7140 (WSL V3) on ttyUSB0

DELAY_BETWEEN_CHUNKS = 3
DELAY_AFTER_HEADER = 3
SECONDS_PER_CHUNK = 5

ack_event = threading.Event()
ack_received_num = -1
transfer_aborted = False
transfer_done = False
mesh_interface = None


def find_port():
    ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    if not ports:
        print("No meshtastic device found.")
        sys.exit(1)
    if len(ports) > 1:
        return ports[1]
    return ports[0]


def on_receive(packet, interface):
    global ack_received_num, transfer_aborted, transfer_done

    if "decoded" not in packet:
        return

    decoded = packet["decoded"]
    if "payload" not in decoded:
        return

    ptype, fields = parse_packet(decoded["payload"])

    if ptype == "ACK":
        ack_received_num = fields["chunk_num"]
        ack_event.set()
        print(f"    <- ACK {fields['chunk_num']}")

    elif ptype == "NAK":
        print(f"    <- NAK {fields['chunk_num']} (will retransmit)")
        ack_event.set()

    elif ptype == "DONE":
        status = fields["status"]
        if status == "md5_ok":
            print("\n    <- DONE: MD5 verified! Transfer successful!")
            transfer_done = True
        else:
            print("\n    <- DONE: MD5 MISMATCH! Transfer failed!")
            transfer_aborted = True
        ack_event.set()

    elif ptype == "ABORT":
        print("\n    <- ABORT received from receiver")
        transfer_aborted = True
        ack_event.set()


def send_packet(data):
    global mesh_interface

    for attempt in range(3):
        try:
            mesh_interface.sendData(
                data,
                destinationId=DEST_ID,
                portNum=PORT_NUM,
                hopLimit=HOP_LIMIT,
                wantAck=False,
            )
            return True
        except Exception as e:
            print(f"    !! Send error (attempt {attempt+1}): {e}")
            if attempt < 2:
                print("    Waiting 10s for USB recovery...")
                time.sleep(10)
                try:
                    mesh_interface.close()
                except:
                    pass
                time.sleep(2)
                port = find_port()
                print(f"    Reconnecting to {port}...")
                mesh_interface = meshtastic.serial_interface.SerialInterface(port)
                time.sleep(3)
                print("    Reconnected!")
            else:
                return False
    return False


def format_duration(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"
    else:
        h, remainder = divmod(int(seconds), 3600)
        m, s = divmod(remainder, 60)
        return f"{h}h {m}m {s}s"


def show_estimate(filepath, file_size, total_chunks):
    est_seconds = total_chunks * SECONDS_PER_CHUNK
    header_bytes = len(f"CHK|{total_chunks}|".encode("utf-8"))

    print(f"\n{'='*50}")
    print(f"  File:       {os.path.basename(filepath)}")
    print(f"  Size:       {file_size:,} bytes ({file_size/1024:.1f} KB)")
    print(f"  Chunks:     {total_chunks}")
    print(f"  Per chunk:  {MAX_CHUNK_DATA}B data + {header_bytes}B header")
    print(f"  Estimated:  {format_duration(est_seconds)}")
    print(f"{'='*50}")

    if est_seconds > 300:
        print(f"\n  WARNING: This will take ~{format_duration(est_seconds)}")
        print(f"  LoRa is slow! Consider files < 10KB.")

    if file_size > 50000:
        print(f"\n  CAUTION: Large file ({file_size/1024:.1f}KB).")
        print(f"  Risk of USB disconnection on long transfers.")

    print()
    answer = input("  Proceed? [y/N]: ").strip().lower()
    return answer == "y"


def send_file(filepath):
    global ack_received_num, transfer_aborted, transfer_done, mesh_interface

    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    with open(filepath, "rb") as f:
        file_data = f.read()

    filename = os.path.basename(filepath)
    md5 = file_md5(filepath)
    total_size = len(file_data)

    chunks = []
    for i in range(0, total_size, MAX_CHUNK_DATA):
        chunks.append(file_data[i : i + MAX_CHUNK_DATA])
    total_chunks = len(chunks)

    if not show_estimate(filepath, total_size, total_chunks):
        print("  Cancelled.")
        return

    pub.subscribe(on_receive, "meshtastic.receive")

    port = find_port()
    print(f"\nConnecting to {port}...")
    mesh_interface = meshtastic.serial_interface.SerialInterface(port)
    time.sleep(3)

    disable_pkc(mesh_interface)

    print(f"Connected! Node: {mesh_interface.myInfo.my_node_num}\n")

    ack_received_num = -1
    transfer_aborted = False
    transfer_done = False

    # Phase 1: Header
    print(f"-> Header: {filename}, {total_chunks} chunks, md5={md5[:8]}...")
    send_packet(make_header(filename, total_chunks, md5))
    time.sleep(DELAY_AFTER_HEADER)

    # Phase 2: Chunks with ACK
    start_time = time.time()

    for i, chunk_data in enumerate(chunks):
        if transfer_aborted or transfer_done:
            if transfer_aborted:
                print("Transfer aborted!")
            break

        chunk_num = i + 1
        retries = 0

        while retries < MAX_RETRIES:
            if transfer_aborted:
                break

            remaining = (total_chunks - chunk_num) * SECONDS_PER_CHUNK
            progress = chunk_num / total_chunks * 100

            pkt = make_chunk(chunk_num, chunk_data)
            print(
                f"  -> CHK {chunk_num}/{total_chunks} "
                f"({len(chunk_data)}B) "
                f"[{progress:.1f}%] "
                f"ETA:{format_duration(remaining)}",
                end="",
            )
            if retries > 0:
                print(f" [retry {retries}]", end="")
            print()

            ack_event.clear()
            ack_received_num = -1

            if not send_packet(pkt):
                print("    !! Failed to send. Aborting.")
                transfer_aborted = True
                break

            got_ack = ack_event.wait(timeout=ACK_TIMEOUT)

            if not got_ack:
                print(f"    !! Timeout waiting for ACK {chunk_num}")
                retries += 1
                time.sleep(2)
                continue

            if transfer_done:
                break
            if ack_received_num == chunk_num:
                break
            else:
                retries += 1
                continue

        if retries >= MAX_RETRIES:
            print(f"\n!! Max retries for chunk {chunk_num}. Aborting.")
            send_packet(make_abort())
            transfer_aborted = True
            break

        time.sleep(DELAY_BETWEEN_CHUNKS)

    # Phase 3: Wait for DONE
    if not transfer_aborted:
        elapsed = time.time() - start_time
        print(f"\nAll chunks sent in {format_duration(elapsed)}")
        if not transfer_done:
            print("Waiting for receiver to verify MD5...")
            ack_event.clear()
            ack_event.wait(timeout=30)

    time.sleep(2)
    try:
        mesh_interface.close()
    except:
        pass

    if not transfer_aborted:
        total_elapsed = time.time() - start_time
        speed = total_size / total_elapsed
        print(f"\nTransfer complete!")
        print(f"  Time:  {format_duration(total_elapsed)}")
        print(f"  Speed: {speed:.1f} bytes/s ({speed/1024:.2f} KB/s)")
    else:
        print("\nTransfer FAILED.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sender.py <file_to_send>")
        sys.exit(1)
    send_file(sys.argv[1])
