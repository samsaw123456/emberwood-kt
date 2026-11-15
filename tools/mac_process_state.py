"""Recognize only proven terminal PIDs; never authorize a signal by liveness alone."""

import os
import subprocess


def terminal_process_state(pid):
    """Return gone/zombie, or None for a live or unidentified process."""
    if type(pid) is not int or pid <= 0:
        raise ValueError("Expected one positive process ID")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "gone"
    # kill(pid, 0) also succeeds for unreaped dead children. Apple's ps documents
    # Z as dead, unlike R/S/T/U or the additional E (trying-to-exit) flag:
    # https://github.com/apple-oss-distributions/adv_cmds/blob/main/ps/ps.1
    result = subprocess.run(
        ["/bin/ps", "-p", str(pid), "-o", "state="],
        capture_output=True,
        text=True,
        check=False,
        timeout=2,
    )
    states = result.stdout.split() if isinstance(result.stdout, str) else []
    if result.returncode == 0 and len(states) == 1 and states[0].startswith("Z"):
        return "zombie"
    # The process may have disappeared while ps was looking it up. Otherwise,
    # failed/empty ps output is not evidence that an unidentified process exited.
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "gone"
    return None
