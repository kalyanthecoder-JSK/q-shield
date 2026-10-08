from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from threading import Lock

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("QSHIELD_FLASK_SECRET", "dev-only-change-me")

# Educational demo state only. Restarting the server clears all keys and audit events.
STATE_LOCK = Lock()
SESSION_KEYS: dict[str, bytes] = {}
AUDIT: list[dict] = []
LATEST_QKD: dict = {
    "status": "Not run",
    "qber": None,
    "sifted_bits": 0,
    "key_bits": 0,
    "eve_enabled": False,
    "message": "Run a QKD simulation to establish a demo session key.",
}
QBER_ABORT_THRESHOLD = 0.11
DEFAULT_BITS = 512
MIN_SIFTED_BITS = 32


def log_event(event_type: str, message: str, severity: str = "info", details: dict | None = None) -> None:
    event = {
        "time": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "type": event_type,
        "severity": severity,
        "message": message,
        "details": details or {},
    }
    with STATE_LOCK:
        AUDIT.insert(0, event)
        del AUDIT[100:]


def bits_to_bytes(bit_string: str) -> bytes:
    """Pack a bit string into bytes, padding the final byte with zeros if needed."""
    if not bit_string:
        return b""
    padded = bit_string + ("0" * ((8 - len(bit_string) % 8) % 8))
    return bytes(int(padded[i:i + 8], 2) for i in range(0, len(padded), 8))


def simulate_bb84(n_bits: int = DEFAULT_BITS, eve_enabled: bool = False) -> dict:
    """
    Simplified BB84 teaching simulation:
    - Alice randomly chooses bits and bases.
    - Bob randomly chooses measurement bases.
    - Optional Eve intercepts each qubit, measures in a random basis, and resends.
    - Alice and Bob publicly compare bases and sift matching positions.
    - A random subset is disclosed to estimate QBER and then discarded.
    - If QBER is acceptable, a demo key is derived from the remaining Alice bits.

    This is NOT a real QKD implementation. It omits authenticated classical-channel
    integration, full error correction, finite-key security analysis, device modeling,
    and standards-compliant privacy amplification.
    """
    if not 128 <= int(n_bits) <= 4096:
        raise ValueError("Number of simulated bits must be between 128 and 4096.")

    alice_bits = [secrets.randbelow(2) for _ in range(n_bits)]
    alice_bases = [secrets.randbelow(2) for _ in range(n_bits)]
    bob_bases = [secrets.randbelow(2) for _ in range(n_bits)]
    bob_bits: list[int] = []
    eve_bases: list[int] = []

    for i in range(n_bits):
        if eve_enabled:
            eve_basis = secrets.randbelow(2)
            eve_bases.append(eve_basis)
            # If Eve chose the correct basis, she learns the bit; otherwise her
            # measurement is random. Bob receives Eve's measured state.
            eve_bit = alice_bits[i] if eve_basis == alice_bases[i] else secrets.randbelow(2)
            bob_bit = eve_bit if bob_bases[i] == eve_basis else secrets.randbelow(2)
        else:
            bob_bit = alice_bits[i] if bob_bases[i] == alice_bases[i] else secrets.randbelow(2)
        bob_bits.append(bob_bit)

    sifted_indices = [i for i in range(n_bits) if alice_bases[i] == bob_bases[i]]
    if len(sifted_indices) < MIN_SIFTED_BITS:
        raise RuntimeError("Too few sifted bits. Run the simulation again.")

    # Reveal and discard 25% of sifted bits to estimate the quantum bit error rate.
    sample_count = max(8, len(sifted_indices) // 4)
    sample_count = min(sample_count, len(sifted_indices) - MIN_SIFTED_BITS)
    sample_indices = set(secrets.SystemRandom().sample(sifted_indices, sample_count))
    errors = sum(alice_bits[i] != bob_bits[i] for i in sample_indices)
    qber = errors / sample_count if sample_count else 0.0
    remaining = [i for i in sifted_indices if i not in sample_indices]

    result = {
        "qber": qber,
        "qber_percent": round(qber * 100, 2),
        "sample_errors": errors,
        "sample_bits": sample_count,
        "sifted_bits": len(sifted_indices),
        "remaining_bits": len(remaining),
        "eve_enabled": bool(eve_enabled),
        "n_bits": n_bits,
        "key": None,
        "key_fingerprint": None,
        "status": "ABORTED",
        "message": "",
    }

    if qber > QBER_ABORT_THRESHOLD:
        result["message"] = (
            f"QBER {qber * 100:.1f}% exceeded the configured "
            f"{QBER_ABORT_THRESHOLD * 100:.0f}% demo threshold. Key establishment aborted."
        )
        return result

    # In this demo, hash the unrevealed Alice sifted bits to obtain a fixed-size key.
    # This is a teaching simplification, not standards-compliant privacy amplification.
    raw_bits = "".join(str(alice_bits[i]) for i in remaining)
    key_material = bits_to_bytes(raw_bits)
    key = hashlib.sha256(b"QSHIELD-DEMO-BB84-v1|" + key_material).digest()
    result["key"] = key
    result["key_fingerprint"] = hashlib.sha256(key).hexdigest()[:16].upper()
    result["status"] = "ESTABLISHED"
    result["message"] = "Demo key established. This result comes from a software simulation, not physical quantum hardware."
    return result


def safe_qkd_summary(result: dict) -> dict:
    return {k: v for k, v in result.items() if k != "key"}


@app.get("/")
def index():
    with STATE_LOCK:
        audit_copy = list(AUDIT)
        qkd_copy = dict(LATEST_QKD)
        key_count = len(SESSION_KEYS)
    return render_template(
        "index.html",
        audit=audit_copy,
        qkd=qkd_copy,
        key_count=key_count,
        threshold=QBER_ABORT_THRESHOLD * 100,
    )


@app.get("/api/status")
def api_status():
    with STATE_LOCK:
        audit_copy = list(AUDIT)
        qkd_copy = dict(LATEST_QKD)
        key_count = len(SESSION_KEYS)
    return jsonify({
        "project": "Q-SHIELD",
        "mode": "SIMULATION ONLY",
        "sites": ["Power Grid", "Water Plant", "Bank", "Emergency Center"],
        "qkd": qkd_copy,
        "active_demo_keys": key_count,
        "audit": audit_copy[:20],
        "warning": "Not suitable for production or live critical infrastructure.",
    })


@app.post("/api/qkd")
def api_qkd():
    body = request.get_json(silent=True) or request.form
    try:
        n_bits = int(body.get("n_bits", DEFAULT_BITS))
        eve_enabled = str(body.get("eve_enabled", "false")).lower() in ("true", "1", "yes", "on")
        result = simulate_bb84(n_bits=n_bits, eve_enabled=eve_enabled)
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400

    pair = str(body.get("site_pair", "Power Grid ↔ Emergency Center"))
    with STATE_LOCK:
        # Clear prior key for this pair before applying this run's result.
        SESSION_KEYS.pop(pair, None)
        if result["key"] is not None:
            SESSION_KEYS[pair] = result["key"]
        LATEST_QKD.clear()
        LATEST_QKD.update({
            "status": result["status"],
            "qber": result["qber_percent"],
            "sifted_bits": result["sifted_bits"],
            "key_bits": 256 if result["key"] else 0,
            "eve_enabled": result["eve_enabled"],
            "site_pair": pair,
            "key_fingerprint": result["key_fingerprint"],
            "message": result["message"],
        })

    severity = "warning" if result["status"] == "ABORTED" else "success"
    log_event(
        "QKD " + result["status"],
        result["message"],
        severity,
        {
            "site_pair": pair,
            "qber_percent": result["qber_percent"],
            "sample_errors": result["sample_errors"],
            "sample_bits": result["sample_bits"],
            "eve_enabled": result["eve_enabled"],
        },
    )
    return jsonify(safe_qkd_summary(result))


@app.post("/api/send")
def api_send():
    body = request.get_json(silent=True) or request.form
    pair = str(body.get("site_pair", "Power Grid ↔ Emergency Center"))
    message = str(body.get("message", "")).strip()
    if not message:
        return jsonify({"error": "Enter a message to encrypt."}), 400
    if len(message) > 2000:
        return jsonify({"error": "Message must be 2000 characters or fewer."}), 400

    with STATE_LOCK:
        key = SESSION_KEYS.get(pair)
    if key is None:
        log_event("Message blocked", "No active demo key for this site pair.", "warning", {"site_pair": pair})
        return jsonify({"error": "No active key for this site pair. Run QKD successfully first."}), 409

    nonce = os.urandom(12)
    aad = ("QSHIELD-DEMO|" + pair).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, message.encode("utf-8"), aad)
    # Demo transport envelope: base64 encodes ciphertext and nonce for display.
    envelope = {
        "site_pair": pair,
        "algorithm": "AES-256-GCM",
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "aad": aad.decode("utf-8"),
    }

    # In this local demo, the receiver decrypts immediately using the same in-memory key.
    decrypted = AESGCM(key).decrypt(nonce, ciphertext, aad).decode("utf-8")
    log_event(
        "Message delivered",
        "Message encrypted and authenticated with AES-256-GCM, then decrypted by the demo receiver.",
        "success",
        {"site_pair": pair, "algorithm": "AES-256-GCM", "message_length": len(message)},
    )
    return jsonify({
        "ok": True,
        "envelope": envelope,
        "decrypted_message": decrypted,
        "note": "Local demonstration only: sender and receiver share the same in-memory demo key.",
    })


@app.post("/api/reset")
def api_reset():
    with STATE_LOCK:
        SESSION_KEYS.clear()
        AUDIT.clear()
        LATEST_QKD.clear()
        LATEST_QKD.update({
            "status": "Not run",
            "qber": None,
            "sifted_bits": 0,
            "key_bits": 0,
            "eve_enabled": False,
            "message": "Run a QKD simulation to establish a demo session key.",
        })
    log_event("System reset", "Demo keys and event log cleared.", "info")
    return jsonify({"ok": True, "message": "Demo state reset."})


if __name__ == "__main__":
    print("Q-SHIELD demo running at http://127.0.0.1:5000")
    print("SIMULATION ONLY — do not connect to live infrastructure.")
    app.run(debug=True, host="127.0.0.1", port=5000)
