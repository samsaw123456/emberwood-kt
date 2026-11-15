package emberwood

import java.awt.Dimension
import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import javax.swing.JFrame
import javax.swing.JPanel
import javax.swing.SwingUtilities

/** Four isolated no-input contexts separate the audio worker, AWT startup and their initialization order. */
object MacAudioContextProbe {
    @JvmStatic
    fun main(args: Array<String>) {
        require(args.size == 1 && args[0] in setOf("worker-only", "gui-only", "gui-first", "concurrent"))
        check(System.getProperty("os.name").startsWith("Mac")) { "Run the context probe on macOS" }
        val mode = args[0]
        val preferences = Files.createTempDirectory("emberwood-audio-context-")
        val audio = AtomicReference<Audio>()
        val window = AtomicReference<JFrame>()
        val phase = AtomicReference("starting")
        val setupError = AtomicReference<Throwable>()

        fun startAudio() {
            phase.set("creating-audio")
            audio.set(Audio())
            phase.set("audio-created")
        }

        fun status(): String {
            val device = audio.get()
            val problem = device?.unavailable
            val state =
                when {
                    device == null && mode == "gui-only" -> "not-requested"
                    device == null -> "not-published"
                    problem != null -> "unavailable"
                    device.ready -> "ready"
                    else -> "pending"
                }
            return "{\"mode\":${quote(mode)},\"phase\":${quote(phase.get())},\"audio\":${quote(state)}," +
                "\"ready\":${device?.ready == true},\"unavailable\":${problem?.let(::quote) ?: "null"}," +
                "\"window_created\":${window.get() != null}," +
                "\"setup_error\":${setupError.get()?.let { quote(it.toString()) } ?: "null"}}"
        }

        println("READY")
        try {
            if (mode == "worker-only") {
                startAudio()
            } else {
                phase.set("opening-window")
                SwingUtilities.invokeLater {
                    try {
                        val frame =
                            if (mode == "concurrent") {
                                val opened = openWindow(Settings(preferences))
                                audio.set(opened.second.audio)
                                opened.first
                            } else {
                                JFrame("Emberwood Kotlin").apply {
                                    defaultCloseOperation = JFrame.DISPOSE_ON_CLOSE
                                    contentPane = JPanel().apply { preferredSize = Dimension(1152, 648) }
                                    pack()
                                    setLocationRelativeTo(null)
                                    isVisible = true
                                }
                            }
                        window.set(frame)
                        phase.set("window-visible")
                    } catch (error: Throwable) {
                        setupError.set(error)
                        phase.set("setup-failed")
                    }
                }
            }
            for (command in System.`in`.bufferedReader().lineSequence()) {
                when (command) {
                    "status" -> println(status())
                    "start" -> {
                        check(mode == "gui-first" && phase.get() == "window-visible" && audio.get() == null) {
                            "Only gui-first may start audio after its window is visible"
                        }
                        startAudio()
                        println(status())
                    }
                    "quit" -> break
                    else -> error("Unknown context-probe command")
                }
            }
        } finally {
            // External diagnostics capture the owned process before requesting cleanup; never send OS input here.
            audio.get()?.close()
            if (mode != "worker-only") {
                val disposed = CountDownLatch(1)
                SwingUtilities.invokeLater {
                    try {
                        window.get()?.dispose()
                    } finally {
                        disposed.countDown()
                    }
                }
                if (!disposed.await(2, TimeUnit.SECONDS)) System.err.println("Context window cleanup remains pending")
            }
            preferences.toFile().deleteRecursively()
        }
    }

    private fun quote(value: String): String =
        buildString {
            append('"')
            for (character in value) {
                when {
                    character == '"' -> append("\\\"")
                    character == '\\' -> append("\\\\")
                    character < ' ' -> append("\\u${character.code.toString(16).padStart(4, '0')}")
                    else -> append(character)
                }
            }
            append('"')
        }
}
