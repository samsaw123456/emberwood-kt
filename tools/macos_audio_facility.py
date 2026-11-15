"""Inspect built-in Mac capture facilities without recording or changing consent."""

import argparse
import ctypes
import json
import platform
import sqlite3
from pathlib import Path


def grants(database):
    """Read only existing grants for the known hosted-runner launchers."""
    clients = (
        "/bin/bash",
        "/opt/hca/hosted-compute-agent",
        "/opt/hca/start_hca.sh",
        "/usr/local/opt/runner/provisioner/provisioner",
        "/usr/local/opt/runner/runprovisioner.sh",
    )
    try:
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT service, count(*) FROM access WHERE auth_value = 2 "
                "AND service IN ('kTCCServiceAudioCapture', 'kTCCServiceScreenCapture') "
                "AND client IN (?, ?, ?, ?, ?) GROUP BY service",
                clients,
            ).fetchall()
        return {"existing_grant_counts": dict(rows)}
    except sqlite3.Error as error:
        return {"read_unavailable": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("build/audio-audit-macos/facility.json")
    )
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this read-only facility check on macOS.")
    core = ctypes.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
    graphics = ctypes.CDLL(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    graphics.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
    report = {
        "macos": platform.mac_ver()[0],
        "core_audio_process_tap_api_present": all(
            hasattr(core, symbol)
            for symbol in (
                "AudioHardwareCreateProcessTap",
                "AudioHardwareDestroyProcessTap",
            )
        ),
        "screen_capture_preflight": graphics.CGPreflightScreenCaptureAccess(),
        "existing_runner_grants": {
            "system": grants(Path("/Library/Application Support/com.apple.TCC/TCC.db")),
            "user": grants(
                Path.home() / "Library/Application Support/com.apple.TCC/TCC.db"
            ),
        },
        "capture_attempted": False,
        "consent_requested": False,
        "result": (
            "Discovery only. API presence or a running output device does not prove "
            "audible PCM. Core Audio capture consent remains unverified until a "
            "game-process-only capture succeeds; no microphone or system mix was opened."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
