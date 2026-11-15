package emberwood

import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.TimeUnit

/** Readiness checks never dismiss a permission alert or send input to an unverified window. */
object NativeInputGate {
    fun awaitReady(
        audio: Audio,
        output: Path,
    ) {
        awaitAudioResolution(audio, output, 15_000)
        if (System.getProperty("os.name").startsWith("Mac")) {
            val evidence = output.resolve("input-startup-native-window.json")
            val process =
                NativeAuditTools
                    .python(
                        "-c",
                        "import json,sys; from tools.mac_game_focus import require_game_window; " +
                            "print(json.dumps(require_game_window(int(sys.argv[1]))))",
                        ProcessHandle.current().pid().toString(),
                    ).redirectOutput(evidence.toFile())
                    .redirectError(output.resolve("input-startup-native-window.log").toFile())
                    .start()
            try {
                check(process.waitFor(5, TimeUnit.SECONDS)) { "Native game-window verification timed out; no input was sent" }
                check(process.exitValue() == 0) { "Native game-window verification failed; no input was sent. See $evidence" }
            } finally {
                if (process.isAlive) {
                    process.destroyForcibly()
                    process.waitFor(1, TimeUnit.SECONDS)
                }
            }
        }
    }

    internal fun awaitAudioResolution(
        audio: Audio,
        output: Path,
        timeoutMillis: Long,
    ): String {
        Files.createDirectories(output)
        val began = System.nanoTime()
        val deadline = began + TimeUnit.MILLISECONDS.toNanos(timeoutMillis)
        while (!audio.ready && audio.unavailable == null && System.nanoTime() < deadline) Thread.sleep(10)
        val status = audio.unavailable?.let { "unavailable: $it" } ?: if (audio.ready) "ready" else "pending"
        Files.writeString(
            output.resolve("input-startup-gate.txt"),
            "Audio: $status\nWait milliseconds: ${(System.nanoTime() - began) / 1e6}\n" +
                "No physical input has been sent by this audit.\n",
        )
        check(status != "pending") { "Audio initialization is still pending after ${timeoutMillis}ms; no input was sent" }
        return status
    }
}
