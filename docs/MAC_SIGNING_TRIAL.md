# Native Mac audio-signing diagnostic

Intel Mac startup still shows a microphone consent dialog while the output-only
AudioQueue sink waits inside `AudioDeviceCreateIOProcID`. Raw-JVM context probes
started successfully on a fresh runner; the installed native app did not. The
exact app's Java/native stacks and desktop screenshots are retained locally.

Run `43710417047` tested an explicit `audio-input=false` entitlement in a private
app copy. Intel still prompted. The signature receipt shows ordinary ad-hoc
flags (`0x2`), so that result does not test Hardened Runtime's resource policy.
Its post-cleanup screenshot also contains the detached system dialog: the old
ordinary-window-only cleanup receipt must not be read as a clean desktop. The
updated diagnostic checks every visible window layer and never closes another
process or responds to a consent dialog.

The separate `hardened` mode tests one narrower hypothesis. It signs only the
outer disposable app with `--options runtime`, `allow-jit=true`, and
`disable-library-validation=true`. It includes no audio-input, sandbox, debugger,
dyld-environment or unsigned-executable-memory entitlement. The original package,
game JAR and bundled runtime remain unchanged. This is a candidate policy for
measurement, not a demonstrated minimum or a shipped packaging change.

[Apple's Hardened Runtime documentation](https://developer.apple.com/documentation/security/hardened-runtime)
says resource/runtime exceptions belong to the host executable, shared libraries
inherit them, and false Boolean entitlements should be omitted. Its
[audio-input entitlement documentation](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.device.audio-input)
requires enabling Hardened Runtime first. The candidate permits JIT mappings and
loading the existing ad-hoc bundled libraries; it grants no recording capability.

The pinned JVM source supports trying the two exceptions without adding broader
ones: [HotSpot's BSD allocation path](https://github.com/openjdk/jdk25u/blob/jdk-25.0.5%2B8/src/hotspot/os/bsd/os_bsd.cpp#L1778)
uses `MAP_JIT` for executable anonymous memory. FFM upcalls use code buffers on
[x86-64](https://github.com/openjdk/jdk25u/blob/jdk-25.0.5%2B8/src/hotspot/cpu/x86/upcallLinker_x86_64.cpp#L177)
and [ARM64](https://github.com/openjdk/jdk25u/blob/jdk-25.0.5%2B8/src/hotspot/cpu/aarch64/upcallLinker_aarch64.cpp#L129),
backed by [HotSpot's code cache](https://github.com/openjdk/jdk25u/blob/jdk-25.0.5%2B8/src/hotspot/share/code/codeCache.cpp#L383).
These paths support the experiment; actual startup, output and lifecycle checks
must establish whether this policy works on both supported Mac architectures.

Run the `Diagnose native output-only app signing` workflow with `mode=hardened`
or the preserved `mode=false-only`. Locally on a Mac with a built package:

```sh
python3 tools/mac_entitlement_trial.py --mode hardened
```

Before launching, the driver requires observed signature flags matching the mode,
exactly the requested entitlement dictionary, and unchanged game/runtime hashes.
It retains signatures for every Mach-O executable/library, app metadata and
the source Java executable's embedded bundle plist. It then captures the real
native game startup and checks ordinary nonmodal focus before any input. Only a
clean startup/cleanup proceeds to the same native app's fourteen physical PCM
control cases. Capture is restricted to that exact verified process; the native
fixture check validates kernel executable identity and its configured test main
class instead of expecting a Java class name in native-launcher arguments.

A missing consent grant, prompt, leftover dialog, signature mismatch, incomplete
capture or audio assertion remains a failure. No privacy database, system setting,
microphone, system audio mix or production launch flag is changed by this trial.
