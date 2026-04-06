# MeshTCP - Test Layers

## Layer 1 — Unit tests: protocol serialization (`test_layer1_protocol.py`)

Tests pure functions in `meshtcp.py`. No hardware, no mocks, no network.

**What is covered:**
- `make_header` / `make_chunk` / `make_ack` / `make_nack` / `make_done` / `make_abort` produce correct bytes
- `parse_packet` correctly decodes each packet type back to fields (roundtrip)
- `parse_packet` handles string input (auto-encodes to bytes)
- `parse_packet` returns `UNKNOWN` for garbage input
- `make_chunk` preserves binary data including bytes that look like the `|` separator
- `make_done` maps `True` → `"md5_ok"` and `False` → `"md5_fail"`
- `bytes_md5` returns correct hex digest for known input
- `file_md5` returns correct hex digest reading from a real temp file
- No packet exceeds `MAX_PAYLOAD` (228 bytes) for chunk sizes up to `MAX_CHUNK_DATA`

**How to run:**
```
python -m pytest tests/test_layer1_protocol.py -v
```

---

## Layer 2 — Protocol logic with mocks (`test_layer2_receiver.py`, `test_layer2_sender.py`)

*Not yet written.*

Tests the state machine in `receiver.on_receive` and `sender.on_receive` using
`unittest.mock` to replace `mesh_interface`. No hardware required.

**Planned coverage:**
- FILE packet initializes transfer state correctly
- CHK packet stores chunk and triggers ACK (sent 3x)
- Duplicate CHK re-ACKs but does not double-count chunks
- All chunks received triggers MD5 verification and DONE (sent 3x)
- ABORT packet resets transfer state
- Sender: ACK unblocks chunk loop and advances to next chunk
- Sender: timeout triggers retry up to MAX_RETRIES then aborts
- Sender: DONE received during ACK wait is treated as success

---

## Layer 3 — Integration: full transfer over loopback (`test_layer3_integration.py`)

*Not yet written.*

Runs sender and receiver in-process using a fake transport (queue-based loopback)
instead of a real SerialInterface. Validates the full protocol end-to-end including
packet loss simulation.

**Planned coverage:**
- Single-chunk file transfers successfully
- Multi-chunk file transfers successfully
- MD5 mismatch detected and DONE md5_fail sent
- Packet loss on ACK channel triggers retransmit and eventually succeeds
- Max retries exceeded causes ABORT
