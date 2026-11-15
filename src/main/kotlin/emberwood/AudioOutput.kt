package emberwood

import javax.sound.sampled.AudioFormat
import javax.sound.sampled.SourceDataLine

/** Playback only; native backends must never enumerate or open recording devices. */
internal interface AudioOutput : AutoCloseable {
    val isOpen: Boolean
    val isRunning: Boolean

    fun open(
        format: AudioFormat,
        bufferSize: Int,
    )

    fun start()

    fun write(
        bytes: ByteArray,
        offset: Int,
        length: Int,
    ): Int

    fun flush()
}

internal class JavaSoundOutput(
    private val line: SourceDataLine,
) : AudioOutput {
    override val isOpen: Boolean get() = line.isOpen
    override val isRunning: Boolean get() = line.isRunning

    override fun open(
        format: AudioFormat,
        bufferSize: Int,
    ) = line.open(format, bufferSize)

    override fun start() = line.start()

    override fun write(
        bytes: ByteArray,
        offset: Int,
        length: Int,
    ): Int = line.write(bytes, offset, length)

    override fun flush() = line.flush()

    override fun close() = line.close()
}
