package emberwood

import java.awt.Rectangle
import java.awt.image.BufferedImage
import java.io.IOException
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import javax.imageio.ImageIO

/** LaunchServices can start an audit app outside the checkout and with a minimal PATH. */
internal object NativeAuditTools {
    val hasExternalController get() = !System.getProperty("audit.inputSocket").isNullOrBlank()
    private var captureSession: CaptureSession? = null

    fun python(vararg arguments: String): ProcessBuilder =
        ProcessBuilder(listOf(System.getProperty("audit.python", "python3")) + arguments)
            .directory(Path.of(System.getProperty("audit.root", ".")).toAbsolutePath().toFile())

    fun bridge(command: String): ProcessBuilder {
        check(hasExternalController) { "No external native audit controller is configured" }
        return python(
            "tools/mac_test_bridge.py",
            command,
            System.getProperty("audit.inputSocket"),
            ProcessHandle.current().pid().toString(),
        )
    }

    /** The external controller owns screen access; the copied game only exchanges private IPC. */
    @Synchronized
    fun capture(
        bounds: Rectangle,
        output: Path,
    ): BufferedImage {
        val session = captureSession ?: CaptureSession().also { captureSession = it }
        return session.capture(bounds, output.toAbsolutePath())
    }

    @Synchronized
    fun closeCapture() {
        val session = captureSession
        captureSession = null
        session?.close()
    }

    private class CaptureSession : AutoCloseable {
        private val process = bridge("capture-serve").redirectError(ProcessBuilder.Redirect.INHERIT).start()
        private val input = process.outputStream.bufferedWriter()
        private val output = process.inputStream.bufferedReader()
        private val replies = LinkedBlockingQueue<String>()
        private val reader =
            Thread.ofPlatform().daemon(true).name("native-capture-replies").start {
                try {
                    output.forEachLine { replies.put(it) }
                } catch (error: IOException) {
                    replies.offer("ERROR ${error.message}")
                } finally {
                    replies.offer("SERVER_CLOSED")
                }
            }

        init {
            try {
                check(response(10_000) == "READY") { "External capture controller did not become ready" }
            } catch (error: Throwable) {
                process.destroyForcibly()
                throw error
            }
        }

        fun capture(
            bounds: Rectangle,
            file: Path,
        ): BufferedImage {
            require(bounds.width > 0 && bounds.height > 0)
            Files.createDirectories(file.parent)
            Files.deleteIfExists(file)
            val path =
                file.toString().toCharArray().joinToString("", "\"", "\"") { char ->
                    when {
                        char == '\\' -> "\\\\"
                        char == '"' -> "\\\""
                        char.code < 32 -> "\\u%04x".format(char.code)
                        else -> char.toString()
                    }
                }
            input.write("[${bounds.x},${bounds.y},${bounds.width},${bounds.height},$path]")
            input.newLine()
            input.flush()
            val reply = response(5_000)
            check(reply == "OK") { "External window capture failed: $reply" }
            val image = checkNotNull(ImageIO.read(file.toFile())) { "External controller returned no readable image" }
            check(image.width == bounds.width && image.height == bounds.height) {
                "External capture size ${image.width}x${image.height} differs from requested ${bounds.width}x${bounds.height}"
            }
            return image
        }

        private fun response(timeoutMillis: Long): String =
            checkNotNull(replies.poll(timeoutMillis, TimeUnit.MILLISECONDS)) {
                "External capture controller did not respond within ${timeoutMillis}ms"
            }

        override fun close() {
            try {
                input.close()
                check(process.waitFor(3, TimeUnit.SECONDS)) { "External capture controller did not stop after EOF" }
                check(process.exitValue() == 0) { "External capture controller exited with ${process.exitValue()}" }
            } finally {
                if (process.isAlive) process.destroyForcibly()
                output.close()
                reader.join(1_000)
            }
        }
    }
}
