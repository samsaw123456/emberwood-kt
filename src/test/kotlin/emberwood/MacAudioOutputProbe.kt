package emberwood

import java.lang.foreign.ValueLayout.JAVA_BYTE
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import javax.sound.sampled.AudioFormat

/** Native ABI/lifecycle probe; the game-window PCM audit separately proves audible control effects. */
object MacAudioOutputProbe {
    @JvmStatic
    fun main(args: Array<String>) {
        if (args.contentEquals(arrayOf("--layouts"))) {
            println(
                "{\"stream_bytes\":${MacAudioOutput.STREAM_LAYOUT.byteSize()}," +
                    "\"buffer_bytes\":${MacAudioOutput.BUFFER_LAYOUT.byteSize()}," +
                    "\"buffer_data_offset\":8,\"buffer_size_offset\":16," +
                    "\"boolean_bytes\":${JAVA_BYTE.byteSize()},\"running_property\":1634824814,\"pcm_flags\":12}",
            )
            return
        }
        require(args.isEmpty()) { "Use --layouts or no arguments for the native lifecycle probe" }
        check(System.getProperty("os.name").startsWith("Mac")) { "Native playback must run on macOS" }
        repeat(3) { cycle ->
            val output = MacAudioOutput()
            val writing = AtomicBoolean(true)
            Executors.newSingleThreadExecutor().use { executor ->
                try {
                    output.open(AudioFormat(22050f, 16, 1, true, false), 4096)
                    output.start()
                    check(output.isOpen && output.isRunning)
                    val writer =
                        executor.submit<Long> {
                            var bytes = 0L
                            val silence = ByteArray(512)
                            while (writing.get()) bytes += output.write(silence, 0, silence.size)
                            bytes
                        }
                    Thread.sleep(200)
                    repeat(4) {
                        output.flush()
                        Thread.sleep(75)
                    }
                    writing.set(false)
                    val began = System.nanoTime()
                    output.close()
                    val closeMillis = (System.nanoTime() - began) / 1e6
                    check(closeMillis < 1000) { "Native close took ${closeMillis}ms" }
                    val written = writer.get(1, TimeUnit.SECONDS)
                    check(written > 4096) { "Native callbacks did not sustain playback" }
                    check(!output.isOpen && !output.isRunning)
                    println("Cycle $cycle PASS: $written bytes, reset recovery, close ${closeMillis}ms")
                } finally {
                    writing.set(false)
                    output.close()
                }
            }
        }
        println("PASS: three native output-only lifecycle cycles; actual cue PCM is audited separately")
    }
}
