"""Observe only the launched profile PID's native focus and resource policy."""

import argparse
import ctypes
import json
import os
import platform
import signal
import subprocess
import time
from pathlib import Path


class NativeStatus:
    def __init__(self):
        self.appkit = ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
        self.objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        self.system = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        self.objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self.objc.objc_getClass.restype = ctypes.c_void_p
        self.objc.sel_registerName.argtypes = [ctypes.c_char_p]
        self.objc.sel_registerName.restype = ctypes.c_void_p
        self.system.getpriority.argtypes = [ctypes.c_int, ctypes.c_uint]
        self.system.getpriority.restype = ctypes.c_int
        self.selectors = {}
        self.object = self.sender(ctypes.c_void_p)
        self.integer = self.sender(ctypes.c_long)
        self.boolean = self.sender(ctypes.c_bool)
        self.void = self.sender(None)
        self.pid_argument = self.sender(ctypes.c_void_p, ctypes.c_int)
        self.seconds_argument = self.sender(ctypes.c_void_p, ctypes.c_double)
        self.object_argument = self.sender(None, ctypes.c_void_p)

    def sender(self, result, *arguments):
        return ctypes.CFUNCTYPE(result, ctypes.c_void_p, ctypes.c_void_p, *arguments)(
            ("objc_msgSend", self.objc)
        )

    def cls(self, name):
        result = self.objc.objc_getClass(name.encode())
        if not result:
            raise RuntimeError(f"Native class unavailable: {name}")
        return result

    def sel(self, name):
        if name not in self.selectors:
            self.selectors[name] = self.objc.sel_registerName(name.encode())
        return self.selectors[name]

    def priority(self, kind, pid):
        ctypes.set_errno(0)
        value = self.system.getpriority(kind, pid)
        error = ctypes.get_errno()
        return {"error": os.strerror(error)} if error else value

    def resident_set_kib(self, pid):
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "rss="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        value = result.stdout.strip()
        return int(value) if result.returncode == 0 and value.isdecimal() else None

    def pump_events(self, seconds):
        run_loop = self.object(self.cls("NSRunLoop"), self.sel("currentRunLoop"))
        until = self.seconds_argument(
            self.cls("NSDate"), self.sel("dateWithTimeIntervalSinceNow:"), seconds
        )
        self.object_argument(run_loop, self.sel("runUntilDate:"), until)

    def sample_and_wait(self, pid):
        started = time.monotonic()
        pool = self.object(self.cls("NSAutoreleasePool"), self.sel("new"))
        try:
            app = self.pid_argument(
                self.cls("NSRunningApplication"),
                self.sel("runningApplicationWithProcessIdentifier:"),
                pid,
            )
            workspace = self.object(
                self.cls("NSWorkspace"), self.sel("sharedWorkspace")
            )
            front = self.object(workspace, self.sel("frontmostApplication"))
            front_pid = (
                self.integer(front, self.sel("processIdentifier")) if front else None
            )
            row = {
                "pid": pid,
                "native_application_present": bool(app),
                "frontmost_pid": front_pid,
                "is_frontmost": front_pid == pid,
                "nice": self.priority(0, pid),
                "resident_set_kib": self.resident_set_kib(pid),
                # XNU resource.h: PRIO_DARWIN_PROCESS=4; background result is 0x1000.
                "darwin_process_policy": self.priority(4, pid),
            }
            if app:
                for label, selector in {
                    "active": "isActive",
                    "hidden": "isHidden",
                    "terminated": "isTerminated",
                    "finished_launching": "isFinishedLaunching",
                }.items():
                    row[label] = self.boolean(app, self.sel(selector))
                row["activation_policy"] = self.integer(
                    app, self.sel("activationPolicy")
                )
            # NSRunningApplication properties update through the main run loop.
            self.pump_events(1.0)
            # An empty run loop can return immediately; never poll the measured app.
            time.sleep(max(0.0, 1.0 - (time.monotonic() - started)))
            return row
        finally:
            self.void(pool, self.sel("drain"))


def observe(command, output, status_factory=NativeStatus):
    output.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    started = time.monotonic()
    rss_samples = []
    with output.open("w", buffering=1) as log:
        try:
            native = status_factory()
        except (OSError, RuntimeError) as error:
            native = None
            failed = True
            log.write(json.dumps({"result": "UNVERIFIED", "reason": str(error)}) + "\n")
        process = subprocess.Popen(command)

        def interrupted(signum, _frame):
            raise SystemExit(128 + signum)

        previous = {
            kind: signal.signal(kind, interrupted)
            for kind in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            while process.poll() is None:
                if native:
                    try:
                        elapsed = time.monotonic() - started
                        row = native.sample_and_wait(process.pid)
                        if row.get("resident_set_kib") is not None:
                            rss_samples.append(row["resident_set_kib"])
                        row["elapsed_seconds"] = elapsed
                        log.write(json.dumps(row) + "\n")
                    except (OSError, RuntimeError) as error:
                        failed = True
                        native = None
                        log.write(
                            json.dumps(
                                {
                                    "pid": process.pid,
                                    "result": "UNVERIFIED",
                                    "reason": str(error),
                                }
                            )
                            + "\n"
                        )
                else:
                    time.sleep(1)
            result = process.wait()
            log.write(
                json.dumps(
                    {
                        "pid": process.pid,
                        "child_exit_code": result,
                        "observer_result": "UNVERIFIED" if failed else "PASS",
                        "rss_sample_count": len(rss_samples),
                        "peak_sampled_resident_set_kib": max(rss_samples, default=None),
                        "rss_method": "Exact-PID one-second samples; not an OS high-water mark",
                    }
                )
                + "\n"
            )
            return result if result else int(failed)
        finally:
            for kind, handler in previous.items():
                signal.signal(kind, handler)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if platform.system() != "Darwin" or not command:
        parser.error("Run on macOS and supply the profile command after --.")
    raise SystemExit(observe(command, args.output))


if __name__ == "__main__":
    main()
