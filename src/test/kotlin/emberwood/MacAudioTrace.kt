package emberwood

import java.awt.Dimension
import java.awt.event.WindowAdapter
import java.awt.event.WindowEvent
import java.lang.foreign.Arena
import java.lang.foreign.Linker
import java.lang.foreign.MemorySegment
import java.lang.foreign.ValueLayout.ADDRESS
import java.lang.foreign.ValueLayout.JAVA_INT
import java.lang.invoke.MethodHandle
import java.lang.invoke.MethodHandles
import java.lang.invoke.MethodType
import java.lang.reflect.Proxy
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.SourceDataLine
import javax.swing.JFrame

/** Opt-in diagnostic only. Production classes, queue size and synthesized PCM remain unchanged. */
internal class MacAudioTrace(
    private val directory: Path,
    private val eventCapacity: Int = 262144,
    pcmCapacity: Int = 8 * 1024 * 1024,
) {
    private val times = LongArray(eventCapacity)
    private val kinds = Array(eventCapacity) { "" }
    private val addresses = LongArray(eventCapacity)
    private val offsets = IntArray(eventCapacity)
    private val lengths = IntArray(eventCapacity)
    private val statuses = IntArray(eventCapacity)
    private val depths = IntArray(eventCapacity)
    private val pcm = ByteArray(pcmCapacity)
    private val scratch = ByteArray(MacAudioOutput.BLOCK_BYTES)
    private val scratchSegment = MemorySegment.ofArray(scratch)
    private var count = 0
    private var used = 0
    private var pending = 0
    private var truncated = false
    private val errors = mutableListOf<String>()
    private val anchors = mutableListOf(anchor())
    private val disposed = CountDownLatch(1)

    @Volatile private var queueCreated = false

    @Volatile private var disposalSucceeded = false

    @Volatile private var audioWorker: Thread? = null

    @Synchronized
    fun event(
        kind: String,
        address: Long = 0,
        status: Int = 0,
        bytes: ByteArray? = null,
        offset: Int = 0,
        length: Int = 0,
    ) {
        if (count == eventCapacity) {
            truncated = true
            return
        }
        val index = count++
        times[index] = System.nanoTime()
        kinds[index] = kind
        addresses[index] = address
        statuses[index] = status
        lengths[index] = length
        offsets[index] = -1
        if (kind == "enqueue") pending++
        if (kind == "callback") pending--
        depths[index] = pending
        if (pending !in 0..8) error("Observed queue depth outside its eight-buffer bound: $pending")
        if (bytes != null && (offset until offset + length).any { bytes[it] != 0.toByte() }) {
            if (used + length > pcm.size) {
                truncated = true
                return
            }
            offsets[index] = used
            bytes.copyInto(pcm, used, offset, offset + length)
            used += length
        }
    }

    @Synchronized
    fun nativeBlock(buffer: MemorySegment) {
        val pointer = buffer.reinterpret(MacAudioOutput.BUFFER_LAYOUT.byteSize())
        val length = pointer.get(JAVA_INT, 16)
        check(length in 0..scratch.size) { "Native trace received an invalid PCM block" }
        val data = pointer.get(ADDRESS, 8).reinterpret(length.toLong())
        MemorySegment.copy(data, 0, scratchSegment, 0, length.toLong())
        event("enqueue", buffer.address(), bytes = scratch, length = length)
    }

    @Synchronized
    fun error(message: String) {
        if (errors.size < 16) errors.add(message)
    }

    fun created() {
        queueCreated = true
    }

    fun disposalFinished(status: Int) {
        if (status != 0) error("Native disposal returned $status")
        disposalSucceeded = status == 0
        disposed.countDown()
    }

    fun line(output: AudioOutput): SourceDataLine =
        Proxy.newProxyInstance(SourceDataLine::class.java.classLoader, arrayOf(SourceDataLine::class.java)) { _, method, args ->
            when (method.name) {
                "open" -> {
                    output.open(args[0] as AudioFormat, args[1] as Int)
                    null
                }
                "start" -> {
                    output.start()
                    null
                }
                "write" -> {
                    val bytes = args[0] as ByteArray
                    val offset = args[1] as Int
                    val length = args[2] as Int
                    event("generated", bytes = bytes, offset = offset, length = length)
                    output.write(bytes, offset, length).also { event("write-return", status = it) }
                }
                "flush" -> {
                    output.flush()
                    null
                }
                "close" -> {
                    output.close()
                    null
                }
                "isOpen" -> output.isOpen
                "isRunning" -> output.isRunning
                else -> kotlin.error("Unexpected traced line operation: ${method.name}")
            }
        } as SourceDataLine

    fun openWindow(settings: Settings): Pair<JFrame, GamePanel> {
        check(System.getProperty("os.name").startsWith("Mac")) { "Native queue tracing requires macOS" }
        val ready = CountDownLatch(1)
        val audio =
            Audio {
                audioWorker = Thread.currentThread()
                check(ready.await(10, TimeUnit.SECONDS)) { "Traced game window was not constructed" }
                // The private implementation is pinned by this diagnostic's exact production-JAR hash.
                // Reflection keeps this instrumentation entirely outside shipped code.
                val constructor = Class.forName("emberwood.AppleAudioQueue").getDeclaredConstructor()
                constructor.isAccessible = true
                val api = constructor.newInstance() as MacAudioQueueApi
                line(MacAudioOutput(TracingMacQueue(api, this)))
            }
        try {
            val panel = GamePanel(settings, audio)
            val frame = JFrame("Emberwood Kotlin")
            frame.defaultCloseOperation = JFrame.DISPOSE_ON_CLOSE
            frame.contentPane = panel
            frame.iconImages = listOf(Assets.image("assets/app/emberwood.png"))
            frame.minimumSize = Dimension(800, 600)
            frame.pack()
            frame.setLocationRelativeTo(null)
            frame.addWindowFocusListener(
                object : WindowAdapter() {
                    override fun windowLostFocus(event: WindowEvent) = panel.loseFocus()

                    override fun windowGainedFocus(event: WindowEvent) {
                        panel.requestFocusInWindow()
                    }
                },
            )
            frame.addWindowListener(
                object : WindowAdapter() {
                    override fun windowClosed(event: WindowEvent) = panel.close()
                },
            )
            frame.isVisible = true
            panel.requestFocusInWindow()
            ready.countDown()
            return frame to panel
        } catch (failure: Throwable) {
            ready.countDown()
            audio.close()
            throw failure
        }
    }

    fun finish() {
        // WindowClosed is delivered asynchronously; wait for the producer as well
        // as native disposal before snapshotting the final event sequence.
        audioWorker?.let {
            it.join(5_000)
            if (it.isAlive) error("Audio producer did not finish before trace snapshot")
        }
        if (!queueCreated || !disposed.await(5, TimeUnit.SECONDS)) error("Native queue disposal was not confirmed")
        synchronized(this) {
            anchors.add(anchor())
            Files.createDirectories(directory)
            Files.newOutputStream(directory.resolve("samples.s16le")).use { it.write(pcm, 0, used) }
            Files.newBufferedWriter(directory.resolve("events.tsv")).use { writer ->
                writer.appendLine("Sequence\tNano time\tEvent\tBuffer address\tPCM offset\tBytes\tStatus\tPending buffers")
                repeat(count) { index ->
                    writer.appendLine(
                        listOf(
                            index,
                            times[index],
                            kinds[index],
                            addresses[index],
                            offsets[index],
                            lengths[index],
                            statuses[index],
                            depths[index],
                        ).joinToString("\t"),
                    )
                }
            }
            val successful = !truncated && errors.isEmpty() && queueCreated && disposalSucceeded
            Files.writeString(
                directory.resolve("summary.json"),
                "{\n  \"result\": \"${if (successful) "PASS" else "FAIL"}\",\n" +
                    "  \"event_count\": $count,\n  \"pcm_bytes\": $used,\n  \"truncated\": $truncated,\n" +
                    "  \"native_queue_disposed\": ${queueCreated && disposalSucceeded},\n" +
                    "  \"errors\": ${errors.joinToString(prefix = "[", postfix = "]", transform = ::quote)},\n" +
                    "  \"clock_anchors\": ${anchors.joinToString(prefix = "[", postfix = "]")},\n" +
                    "  \"sample_rate\": 22050,\n  \"channels\": 1,\n  \"sample_format\": \"signed16-little-endian\",\n" +
                    "  \"zero_encoding\": \"PCM offset -1 denotes exactly zero bytes, not omitted samples\",\n" +
                    "  \"scope\": \"Opt-in provider adapter around unchanged production mixer and native queue; " +
                    "not performance evidence\"\n}\n",
            )
        }
    }

    private fun anchor(): String {
        val before = System.nanoTime()
        val wall = System.currentTimeMillis()
        val after = System.nanoTime()
        return "{\"nano_before\":$before,\"unix_milliseconds\":$wall,\"nano_after\":$after,\"wall_resolution_ms\":1}"
    }

    private fun quote(value: String): String = "\"${value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")}\""
}

/** Callback forwarding uses real FFM transitions; no exception may escape an upcall. */
internal class TracingMacQueue(
    private val delegate: MacAudioQueueApi,
    private val trace: MacAudioTrace,
) : MacAudioQueueApi by delegate {
    private val memory = Arena.ofShared()
    private lateinit var original: MethodHandle

    override fun create(
        format: MemorySegment,
        callback: MemorySegment,
        result: MemorySegment,
    ): Int {
        original = Linker.nativeLinker().downcallHandle(callback, MacAudioOutput.CALLBACK_DESCRIPTOR)
        val method =
            MethodHandles
                .lookup()
                .findVirtual(
                    TracingMacQueue::class.java,
                    "returned",
                    MethodType.methodType(Void.TYPE, MemorySegment::class.java, MemorySegment::class.java, MemorySegment::class.java),
                ).bindTo(this)
        val replacement = Linker.nativeLinker().upcallStub(method, MacAudioOutput.CALLBACK_DESCRIPTOR, memory)
        return delegate.create(format, replacement, result).also { status ->
            trace.event("create-return", status = status)
            if (status == 0) {
                trace.created()
            } else {
                trace.error("Native creation returned $status")
                memory.close()
            }
        }
    }

    override fun enqueue(
        queue: MemorySegment,
        buffer: MemorySegment,
    ): Int {
        trace.nativeBlock(buffer)
        return delegate.enqueue(queue, buffer).also {
            trace.event("enqueue-return", buffer.address(), it)
            if (it != 0) trace.error("Native enqueue returned $it")
        }
    }

    override fun reset(queue: MemorySegment): Int {
        trace.event("reset-begin")
        return delegate.reset(queue).also {
            trace.event("reset-return", status = it)
            if (it != 0) trace.error("Native reset returned $it")
        }
    }

    override fun dispose(queue: MemorySegment): Int {
        trace.event("dispose-begin")
        return delegate.dispose(queue).also {
            trace.event("dispose-return", status = it)
            if (it == 0) memory.close()
            trace.disposalFinished(it)
        }
    }

    @Suppress("UNUSED_PARAMETER")
    private fun returned(
        user: MemorySegment,
        queue: MemorySegment,
        buffer: MemorySegment,
    ) {
        try {
            trace.event("callback", buffer.address())
        } catch (failure: Throwable) {
            trace.error("Callback trace failed: ${failure.javaClass.simpleName}")
        }
        try {
            original.invokeWithArguments(user, queue, buffer)
        } catch (failure: Throwable) {
            trace.error("Callback forwarding failed: ${failure.javaClass.simpleName}")
        }
    }
}
