"""
Central configuration for MeshTCP.

Every value has a code default and can be overridden by an environment
variable (all prefixed with MESH_). The lists document the valid choices.

Examples:
    MESH_PRESET=SHORT_FAST uv run python sender.py file.txt
    MESH_CHUNK_DELAY=0.1 MESH_ACK_TIMEOUT=20 uv run python receiver.py
"""

import os


# --------------------------------------------------------------- env helpers
def _str(key, default):
    return os.getenv(key, default)


def _int(key, default):
    return int(os.getenv(key, str(default)))


def _float(key, default):
    return float(os.getenv(key, str(default)))


def _bool(key, default):
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------- radio / nodes
# Node numbers (decimal `num` from `meshtastic --info`).
SENDER_NODE_ID = _int("MESH_SENDER_ID", 2896785728)    # 7140 / ttyUSB1
RECEIVER_NODE_ID = _int("MESH_RECEIVER_ID", 4143665568)  # 51a0 / ttyUSB0

# Valid LoRa modem presets, fastest -> longest range (theoretical data rate).
MODEM_PRESETS = [
    "SHORT_TURBO",    # 21.88 kbps, 500kHz  (not legal in every region)
    "SHORT_FAST",     # 10.94 kbps, 250kHz
    "SHORT_SLOW",     #  6.25 kbps, 250kHz
    "MEDIUM_FAST",    #  3.52 kbps, 250kHz
    "MEDIUM_SLOW",    #  1.95 kbps, 250kHz
    "LONG_TURBO",     #  1.34 kbps, 500kHz
    "LONG_FAST",      #  1.07 kbps, 250kHz  (Meshtastic default)
    "LONG_MODERATE",  #  0.34 kbps, 125kHz
    "LONG_SLOW",      #  0.18 kbps, 125kHz
]
MODEM_PRESET = _str("MESH_PRESET", "LONG_FAST")

# Valid LoRa region codes (set to your country's band). BR_902 = Brazil.
LORA_REGIONS = [
    "US", "EU_433", "EU_868", "CN", "JP", "ANZ", "KR", "TW", "RU", "IN",
    "NZ_865", "TH", "LORA_24", "UA_433", "UA_868", "MY_433", "MY_919",
    "SG_923", "PH_433", "PH_868", "PH_915", "ANZ_433", "KZ_433", "KZ_863",
    "NP_865", "BR_902",
]
LORA_REGION = _str("MESH_REGION", "BR_902")

# Apply preset + region to the radio on connect. Reboots the radio (~12s) only
# when the current setting differs from the config.
APPLY_RADIO_CONFIG = _bool("MESH_APPLY_RADIO", True)

# Disable PKC encryption on connect so packets arrive decoded.
DISABLE_PKC = _bool("MESH_DISABLE_PKC", True)


# --------------------------------------------------------------- protocol
PORT_NUM = _int("MESH_PORT_NUM", 256)          # PRIVATE_APP
MAX_PAYLOAD = _int("MESH_MAX_PAYLOAD", 228)    # meshtastic max payload (limit is 233)
MAX_CHUNK_DATA = _int("MESH_CHUNK_SIZE", 200)  # usable data per chunk (conservative)
HOP_LIMIT = _int("MESH_HOP_LIMIT", 3)


# --------------------------------------------------------------- timing (seconds)
# Tuning guide (smaller = faster but more collisions/retransmits):
#   SHORT_* presets, close range -> CHUNK_DELAY ~0.2-0.5, ACK_TIMEOUT ~10
#   LONG_*  presets, long range  -> CHUNK_DELAY ~2-3,     ACK_TIMEOUT ~15-20
ACK_TIMEOUT = _float("MESH_ACK_TIMEOUT", 15)            # window to wait for matching ACK
MAX_RETRIES = _int("MESH_MAX_RETRIES", 20)              # resends per chunk before abort
DELAY_BETWEEN_CHUNKS = _float("MESH_CHUNK_DELAY", 0.3)  # pause after each ACKed chunk
DELAY_AFTER_HEADER = _float("MESH_HEADER_DELAY", 3)     # pause after sending the header
RETRY_BACKOFF = _float("MESH_RETRY_BACKOFF", 2)         # pause after a timeout before resend
SECONDS_PER_CHUNK = _float("MESH_SECONDS_PER_CHUNK", 1)  # ETA estimate only


# --------------------------------------------------------------- I/O
OUTPUT_DIR = _str("MESH_OUTPUT_DIR", "received_files")


# --------------------------------------------------------------- validation
def validate():
    if MODEM_PRESET not in MODEM_PRESETS:
        raise ValueError(
            f"MESH_PRESET={MODEM_PRESET!r} is invalid. "
            f"Choose one of: {', '.join(MODEM_PRESETS)}"
        )
    if LORA_REGION not in LORA_REGIONS:
        raise ValueError(
            f"MESH_REGION={LORA_REGION!r} is invalid. "
            f"Choose one of: {', '.join(LORA_REGIONS)}"
        )


validate()
