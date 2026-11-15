package emberwood

import java.awt.event.KeyEvent
import java.io.IOException
import java.nio.file.Path
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

/** One independent native connection avoids Robot's X11 AWT lock and per-key process startup. */
class PhysicalKeys(
    trace: Path? = null,
) : AutoCloseable {
    private val started = System.nanoTime()
    private val process =
        NativeAuditTools
            .python("tools/physical_key.py", "--serve")
            .redirectError(ProcessBuilder.Redirect.INHERIT)
            .apply {
                if (trace != null) environment()["EMBERWOOD_PHYSICAL_TRACE"] = trace.toAbsolutePath().toString()
            }.start()
    private val input = process.outputStream.bufferedWriter()
    private val output = process.inputStream.bufferedReader()
    private val replies = LinkedBlockingQueue<String>()
    private val reader =
        Thread.ofPlatform().daemon(true).name("native-keyboard-replies").start {
            try {
                output.forEachLine { replies.put(it) }
            } catch (error: IOException) {
                replies.offer("ERROR ${error.message}")
            } finally {
                replies.offer("SERVER_CLOSED")
            }
        }
    private val held = linkedSetOf<String>()
    private var closed = false
    private var failed = false
    val startupNanos: Long
    var lastBatchNanos: Long = 0
        private set

    init {
        try {
            check(response(10_000) == "READY") { "Native keyboard server did not become ready" }
            startupNanos = System.nanoTime() - started
        } catch (error: Throwable) {
            process.destroyForcibly()
            throw error
        }
    }

    @Synchronized
    fun send(vararg events: Pair<String, Boolean>) {
        check(!closed && !failed) { "Native keyboard server is unavailable" }
        require(events.isNotEmpty()) { "A physical key batch must not be empty" }
        events.forEach { (key, _) -> require(key in bindings) { "Unsupported physical key: $key" } }
        // Even a failed acknowledgement may follow a delivered press: retain it for cleanup.
        events.filter { it.second }.forEach { held.add(it.first) }
        val began = System.nanoTime()
        try {
            input.write(events.joinToString(" ") { (key, down) -> "$key ${if (down) "down" else "up"}" })
            input.newLine()
            input.flush()
            val reply = response(5_000)
            check(reply == "OK") { "Native physical key injection failed: $reply" }
            events.forEach { (key, down) -> if (down) held.add(key) else held.remove(key) }
        } finally {
            lastBatchNanos = System.nanoTime() - began
        }
    }

    fun press(key: String) = send(key to true)

    fun release(key: String) = send(key to false)

    @Synchronized
    fun releaseAll() {
        if (held.isNotEmpty()) send(*held.map { it to false }.toTypedArray())
    }

    private fun response(timeoutMillis: Long): String {
        val reply = replies.poll(timeoutMillis, TimeUnit.MILLISECONDS)
        if (reply == null || reply == "SERVER_CLOSED") {
            failed = true
            error("Native keyboard server stopped or did not respond within ${timeoutMillis}ms")
        }
        return reply
    }

    @Synchronized
    override fun close() {
        if (closed) return
        var failure: Throwable? = null
        try {
            if (!failed) releaseAll()
        } catch (error: Throwable) {
            failure = error
        } finally {
            closed = true
            // EOF makes the server independently release every attempted down, including after errors.
            try {
                input.close()
            } catch (error: IOException) {
                if (failure == null) failure = error else failure.addSuppressed(error)
            }
            if (!process.waitFor(3, TimeUnit.SECONDS)) {
                process.destroy()
                if (!process.waitFor(1, TimeUnit.SECONDS)) process.destroyForcibly()
                val error = IllegalStateException("Native keyboard server did not exit after closing its input")
                if (failure == null) failure = error else failure.addSuppressed(error)
            } else if (process.exitValue() != 0) {
                val error = IllegalStateException("Native keyboard server exited with ${process.exitValue()}")
                if (failure == null) failure = error else failure.addSuppressed(error)
            }
            output.close()
            reader.join(1_000)
        }
        failure?.let { throw it }
    }

    companion object {
        private val bindings =
            mapOf(
                "left-shift" to (KeyEvent.VK_SHIFT to KeyEvent.KEY_LOCATION_LEFT),
                "right-shift" to (KeyEvent.VK_SHIFT to KeyEvent.KEY_LOCATION_RIGHT),
                "keypad-enter" to (KeyEvent.VK_ENTER to KeyEvent.KEY_LOCATION_NUMPAD),
                "return" to (KeyEvent.VK_ENTER to KeyEvent.KEY_LOCATION_STANDARD),
                "escape" to (KeyEvent.VK_ESCAPE to KeyEvent.KEY_LOCATION_STANDARD),
                "space" to (KeyEvent.VK_SPACE to KeyEvent.KEY_LOCATION_STANDARD),
                "tab" to (KeyEvent.VK_TAB to KeyEvent.KEY_LOCATION_STANDARD),
                "left" to (KeyEvent.VK_LEFT to KeyEvent.KEY_LOCATION_STANDARD),
                "right" to (KeyEvent.VK_RIGHT to KeyEvent.KEY_LOCATION_STANDARD),
                "up" to (KeyEvent.VK_UP to KeyEvent.KEY_LOCATION_STANDARD),
                "down" to (KeyEvent.VK_DOWN to KeyEvent.KEY_LOCATION_STANDARD),
                "a" to (KeyEvent.VK_A to KeyEvent.KEY_LOCATION_STANDARD),
                "d" to (KeyEvent.VK_D to KeyEvent.KEY_LOCATION_STANDARD),
                "w" to (KeyEvent.VK_W to KeyEvent.KEY_LOCATION_STANDARD),
                "j" to (KeyEvent.VK_J to KeyEvent.KEY_LOCATION_STANDARD),
                "m" to (KeyEvent.VK_M to KeyEvent.KEY_LOCATION_STANDARD),
                "p" to (KeyEvent.VK_P to KeyEvent.KEY_LOCATION_STANDARD),
                "r" to (KeyEvent.VK_R to KeyEvent.KEY_LOCATION_STANDARD),
            )

        fun binding(key: String): Pair<Int, Int> = bindings.getValue(key)

        fun name(keyCode: Int): String =
            bindings.entries
                .first { (name, binding) ->
                    binding.first == keyCode && name != "right-shift" && name != "keypad-enter"
                }.key
    }
}
