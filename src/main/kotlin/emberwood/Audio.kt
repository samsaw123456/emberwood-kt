package emberwood

import java.util.concurrent.atomic.AtomicBoolean
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.AudioSystem
import javax.sound.sampled.SourceDataLine
import kotlin.math.PI
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

/** Original Emberwood tones, mixed into one bounded, quiet desktop output stream. */
class Audio(
    private val createLine: ((AudioFormat) -> SourceDataLine)? = null,
) : AutoCloseable {
    private data class Voice(
        val pcm: ShortArray,
        var offset: Int = 0,
    )

    private val running = AtomicBoolean(true)
    private val voices = ArrayDeque<Voice>()
    private val clips =
        mapOf(
            "jump" to tone(doubleArrayOf(440.0, 610.0), .065),
            "double" to tone(doubleArrayOf(610.0, 880.0), .07),
            "gem" to tone(doubleArrayOf(880.0, 1175.0), .085),
            "acorn" to tone(doubleArrayOf(523.0, 659.0, 784.0, 1047.0), .11),
            "camp" to tone(doubleArrayOf(392.0, 523.0, 659.0), .13),
            "hurt" to tone(doubleArrayOf(233.0, 196.0, 146.0), .09),
            "bounce" to tone(doubleArrayOf(330.0, 523.0, 784.0), .06),
            "dash" to tone(doubleArrayOf(330.0, 220.0), .035),
            "shoot" to tone(doubleArrayOf(660.0, 440.0), .035),
            "spear" to tone(doubleArrayOf(392.0, 247.0), .045),
            "seed_bomb" to tone(doubleArrayOf(294.0, 440.0, 330.0), .04),
            "thorn_fan" to tone(doubleArrayOf(740.0, 620.0, 490.0), .025),
            "sunwood_lance" to tone(doubleArrayOf(294.0, 196.0), .06),
            "armor" to tone(doubleArrayOf(784.0, 1047.0), .07),
            "win" to tone(doubleArrayOf(523.0, 659.0, 784.0, 1047.0, 784.0, 1047.0), .16),
        )

    @Volatile var muted = false
        set(value) {
            field = value
            if (value) stop()
        }

    @Volatile var unavailable: String? = null
        private set

    @Volatile private var line: AudioOutput? = null
    val ready: Boolean
        get() {
            val device = line
            return running.get() && device != null && device.isOpen && device.isRunning
        }
    private val thread =
        Thread({ output() }, "emberwood-audio").apply {
            isDaemon = true
            start()
        }

    fun play(cue: String) {
        val pcm = clips[cue] ?: return
        if (!muted) {
            synchronized(voices) {
                if (voices.size == 6) voices.removeFirst()
                voices.addLast(Voice(pcm))
            }
        }
    }

    fun stop() {
        synchronized(voices) { voices.clear() }
        try {
            line?.flush()
        } catch (error: Exception) {
            reportUnavailable(error)
            close()
        } catch (error: LinkageError) {
            reportUnavailable(error)
            close()
        }
    }

    private fun output() {
        var device: AudioOutput? = null
        try {
            val format = AudioFormat(22050f, 16, 1, true, false)
            device =
                when {
                    createLine != null -> JavaSoundOutput(createLine(format))
                    System.getProperty("os.name").startsWith("Mac") -> MacAudioOutput()
                    else -> JavaSoundOutput(AudioSystem.getSourceDataLine(format))
                }
            device.open(format, 4096)
            if (!running.get()) return
            device.start()
            // A provider can block during initialization. Never publish its line
            // while close/flush could wait on that same native initialization lock.
            line = device
            if (!running.get()) return
            val bytes = ByteArray(512)
            while (running.get()) {
                synchronized(voices) {
                    for (frame in 0 until bytes.size / 2) {
                        var sum = 0
                        for (voice in voices) if (voice.offset < voice.pcm.size) sum += voice.pcm[voice.offset++].toInt()
                        if (muted) sum = 0
                        val sample = sum.coerceIn(-32768, 32767)
                        bytes[frame * 2] = sample.toByte()
                        bytes[frame * 2 + 1] = (sample shr 8).toByte()
                    }
                    voices.removeAll { it.offset >= it.pcm.size }
                }
                device.write(bytes, 0, bytes.size)
            }
        } catch (error: Exception) {
            reportUnavailable(error)
        } catch (error: LinkageError) {
            reportUnavailable(error)
        } finally {
            line = null
            device?.close()
        }
    }

    private fun reportUnavailable(error: Throwable) {
        if (running.get()) {
            unavailable = error.message ?: error.javaClass.simpleName
            System.err.println("Audio unavailable: $unavailable")
        }
    }

    override fun close() {
        if (!running.getAndSet(false)) return
        val device = line
        if (device != null) {
            // Native device shutdown can itself block. Window disposal must not
            // wait on a provider lock; closing also wakes a blocked audio write.
            Thread({ device.close() }, "emberwood-audio-close").apply {
                isDaemon = true
                start()
            }
        }
        thread.join(1000)
    }

    companion object {
        fun tone(
            notes: DoubleArray,
            duration: Double,
        ): ShortArray {
            val frames = (duration * 22050).toInt()
            return ShortArray(frames * notes.size) { index ->
                val frame = index % frames
                val t = frame / 22050.0
                val envelope = min(t / .012, 1.0) * (1.0 - frame.toDouble() / frames).pow(1.6)
                (sin(2 * PI * notes[index / frames] * t) * envelope * .65 * 32767 * .158489).toInt().toShort()
            }
        }
    }
}
