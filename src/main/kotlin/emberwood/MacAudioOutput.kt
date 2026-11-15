package emberwood

import java.lang.foreign.Arena
import java.lang.foreign.FunctionDescriptor
import java.lang.foreign.Linker
import java.lang.foreign.MemoryLayout
import java.lang.foreign.MemorySegment
import java.lang.foreign.SymbolLookup
import java.lang.foreign.ValueLayout.ADDRESS
import java.lang.foreign.ValueLayout.JAVA_BYTE
import java.lang.foreign.ValueLayout.JAVA_DOUBLE
import java.lang.foreign.ValueLayout.JAVA_INT
import java.lang.invoke.MethodHandles
import java.lang.invoke.MethodType
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.locks.ReentrantLock
import javax.sound.sampled.AudioFormat
import kotlin.concurrent.withLock
import kotlin.math.min

/** Playback through AudioToolbox only: Java Sound's Mac mixers also inspect recording formats. */
internal class MacAudioOutput private constructor(
    createApi: () -> MacAudioQueueApi,
) : AudioOutput {
    constructor() : this({ AppleAudioQueue() })

    internal constructor(api: MacAudioQueueApi) : this({ api })

    private class Buffer(
        val pointer: MemorySegment,
        val data: MemorySegment,
    ) {
        val queued = AtomicBoolean(false)
    }

    private val api by lazy(createApi)
    private val nativeLock = ReentrantLock()
    private val closed = AtomicBoolean(false)
    private val generation = AtomicLong()
    private val callbackFailure = AtomicReference<Throwable>()
    private val buffers = ConcurrentHashMap<Long, Buffer>()
    private val available = ArrayBlockingQueue<Buffer>(8)
    private var arena: Arena? = null
    private var queue = MemorySegment.NULL

    @Volatile override var isOpen = false
        private set

    @Volatile override var isRunning = false
        private set

    override fun open(
        format: AudioFormat,
        bufferSize: Int,
    ) {
        require(
            format.encoding == AudioFormat.Encoding.PCM_SIGNED &&
                format.sampleRate == 22050f &&
                format.channels == 1 &&
                format.sampleSizeInBits == 16 &&
                !format.isBigEndian &&
                format.frameSize == 2,
        ) { "Mac playback requires Emberwood's 22050 Hz mono signed 16-bit little-endian PCM" }
        require(bufferSize in BLOCK_BYTES..4096 && bufferSize % BLOCK_BYTES == 0) { "Invalid bounded audio buffer size" }
        nativeLock.withLock {
            check(!closed.get() && !isOpen) { "Audio output is closed or already open" }
            val memory = Arena.ofShared()
            arena = memory
            try {
                val stream = memory.allocate(STREAM_LAYOUT)
                stream.set(JAVA_DOUBLE, 0, 22050.0)
                stream.set(JAVA_INT, 8, 0x6c70636d) // 'lpcm'
                stream.set(JAVA_INT, 12, 12) // Signed integer | packed; little endian is zero.
                stream.set(JAVA_INT, 16, 2)
                stream.set(JAVA_INT, 20, 1)
                stream.set(JAVA_INT, 24, 2)
                stream.set(JAVA_INT, 28, 1)
                stream.set(JAVA_INT, 32, 16)
                val target =
                    MethodHandles
                        .lookup()
                        .findVirtual(
                            MacAudioOutput::class.java,
                            "returned",
                            MethodType.methodType(
                                Void.TYPE,
                                MemorySegment::class.java,
                                MemorySegment::class.java,
                                MemorySegment::class.java,
                            ),
                        ).bindTo(this)
                val callback = Linker.nativeLinker().upcallStub(target, CALLBACK_DESCRIPTOR, memory)
                val result = memory.allocate(ADDRESS)
                checkStatus(api.create(stream, callback, result), "AudioQueueNewOutput")
                queue = result.get(ADDRESS, 0)
                check(queue != MemorySegment.NULL) { "AudioQueueNewOutput returned no playback queue" }
                repeat(bufferSize / BLOCK_BYTES) {
                    checkStatus(api.allocate(queue, BLOCK_BYTES, result), "AudioQueueAllocateBuffer")
                    val address = result.get(ADDRESS, 0)
                    check(address != MemorySegment.NULL) { "Audio queue returned no playback buffer" }
                    val pointer = address.reinterpret(BUFFER_LAYOUT.byteSize(), memory, null)
                    check(pointer.get(JAVA_INT, 0) >= BLOCK_BYTES) { "Audio queue allocated an undersized buffer" }
                    val dataAddress = pointer.get(ADDRESS, 8)
                    check(dataAddress != MemorySegment.NULL) { "Audio queue returned no PCM storage" }
                    val data = dataAddress.reinterpret(BLOCK_BYTES.toLong(), memory, null)
                    val buffer = Buffer(pointer, data)
                    buffers[pointer.address()] = buffer
                    check(available.offer(buffer)) { "Audio buffer pool overflow" }
                }
                check(!closed.get()) { "Audio output closed during initialization" }
                isOpen = true
            } catch (error: Throwable) {
                closed.set(true)
                try {
                    disposeLocked()
                } catch (cleanup: Throwable) {
                    error.addSuppressed(cleanup)
                }
                throw error
            }
        }
    }

    override fun start() {
        nativeLock.withLock {
            check(isOpen && !closed.get()) { "Audio output is not open" }
            if (isRunning) return
            // Prime before starting; startup is real playback, not a readiness flag set ahead of the device.
            repeat(buffers.size) {
                val buffer = checkNotNull(available.poll()) { "Audio buffer missing before startup" }
                buffer.data.fill(0)
                enqueue(buffer, BLOCK_BYTES)
            }
            checkStatus(api.start(queue), "AudioQueueStart")
        }
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3)
        Arena.ofConfined().use { memory ->
            val value = memory.allocate(JAVA_INT)
            val size = memory.allocate(JAVA_INT)
            while (!closed.get()) {
                val started =
                    nativeLock.withLock {
                        if (closed.get()) return
                        size.set(JAVA_INT, 0, 4)
                        checkStatus(api.running(queue, value, size), "AudioQueueGetProperty(IsRunning)")
                        value.get(JAVA_INT, 0) != 0
                    }
                if (started) {
                    checkCallback()
                    nativeLock.withLock { if (!closed.get()) isRunning = true }
                    return
                }
                check(System.nanoTime() < deadline) { "Audio queue did not start within three seconds" }
                Thread.sleep(10)
            }
        }
    }

    override fun write(
        bytes: ByteArray,
        offset: Int,
        length: Int,
    ): Int {
        require(offset >= 0 && length >= 0 && offset <= bytes.size - length && length % 2 == 0)
        if (closed.get()) return 0
        checkCallback()
        check(isOpen && isRunning) { "Audio output is not running" }
        val startedGeneration = generation.get()
        var written = 0
        while (written < length && !closed.get()) {
            checkCallback()
            // Never hold the native-operation lock while waiting: mute and close must wake a full writer.
            val buffer = available.poll(25, TimeUnit.MILLISECONDS) ?: continue
            if (closed.get()) return written
            if (!nativeLock.tryLock(25, TimeUnit.MILLISECONDS)) {
                check(available.offer(buffer)) { "Audio buffer pool overflow while awaiting the native operation" }
                continue
            }
            try {
                if (closed.get()) return written
                if (generation.get() != startedGeneration) {
                    check(available.offer(buffer)) { "Audio buffer pool overflow after reset" }
                    return length // Flush intentionally discards the remainder of a pre-reset write.
                }
                check(isOpen && isRunning) { "Audio output is not running" }
                val count = min(BLOCK_BYTES, length - written)
                MemorySegment.copy(MemorySegment.ofArray(bytes), (offset + written).toLong(), buffer.data, 0, count.toLong())
                enqueue(buffer, count)
                written += count
            } finally {
                nativeLock.unlock()
            }
        }
        return written
    }

    override fun flush() {
        nativeLock.withLock {
            if (!isOpen || closed.get()) return
            generation.incrementAndGet()
            // AudioQueueFlush plays buffered data; Reset discards it and returns buffers through the callback.
            checkStatus(api.reset(queue), "AudioQueueReset")
        }
    }

    override fun close() {
        if (!closed.compareAndSet(false, true)) return
        isRunning = false
        nativeLock.withLock { disposeLocked() }
    }

    private fun enqueue(
        buffer: Buffer,
        count: Int,
    ) {
        buffer.pointer.set(JAVA_INT, 16, count)
        check(buffer.queued.compareAndSet(false, true)) { "Audio buffer reused before its callback" }
        checkStatus(api.enqueue(queue, buffer.pointer), "AudioQueueEnqueueBuffer")
    }

    @Suppress("UNUSED_PARAMETER")
    private fun returned(
        user: MemorySegment,
        owner: MemorySegment,
        pointer: MemorySegment,
    ) {
        // No exception may cross an FFM upcall: the VM would terminate. No native-operation lock is acquired here.
        try {
            val buffer = buffers[pointer.address()] ?: error("Audio queue returned an unknown buffer")
            if (buffer.queued.compareAndSet(true, false)) {
                check(available.offer(buffer)) { "Audio buffer pool overflow in callback" }
            }
        } catch (error: Throwable) {
            callbackFailure.compareAndSet(null, error)
            isRunning = false
        }
    }

    private fun checkCallback() {
        callbackFailure.get()?.let { throw IllegalStateException("Audio playback callback failed", it) }
    }

    private fun disposeLocked() {
        isRunning = false
        isOpen = false
        if (queue != MemorySegment.NULL) {
            // Apple's synchronous disposal guarantees no further callbacks. On failure retain the arena safely.
            checkStatus(api.dispose(queue), "AudioQueueDispose")
            queue = MemorySegment.NULL
        }
        arena?.close()
        arena = null
        buffers.clear()
        available.clear()
    }

    companion object {
        internal const val BLOCK_BYTES = 512
        internal val STREAM_LAYOUT = MemoryLayout.structLayout(JAVA_DOUBLE, *Array(8) { JAVA_INT })
        internal val BUFFER_LAYOUT =
            MemoryLayout.structLayout(
                JAVA_INT,
                MemoryLayout.paddingLayout(4),
                ADDRESS,
                JAVA_INT,
                MemoryLayout.paddingLayout(4),
                ADDRESS,
                JAVA_INT,
                MemoryLayout.paddingLayout(4),
                ADDRESS,
                JAVA_INT,
                MemoryLayout.paddingLayout(4),
            )
        internal val CALLBACK_DESCRIPTOR = FunctionDescriptor.ofVoid(ADDRESS, ADDRESS, ADDRESS)

        private fun checkStatus(
            status: Int,
            operation: String,
        ) {
            check(status == 0) { "$operation failed with OSStatus $status" }
        }
    }
}

/** Small native-call seam lets lifecycle tests drive genuine FFM callbacks without an audio device. */
internal interface MacAudioQueueApi {
    fun create(
        format: MemorySegment,
        callback: MemorySegment,
        result: MemorySegment,
    ): Int

    fun allocate(
        queue: MemorySegment,
        capacity: Int,
        result: MemorySegment,
    ): Int

    fun enqueue(
        queue: MemorySegment,
        buffer: MemorySegment,
    ): Int

    fun start(queue: MemorySegment): Int

    fun running(
        queue: MemorySegment,
        value: MemorySegment,
        size: MemorySegment,
    ): Int

    fun reset(queue: MemorySegment): Int

    fun dispose(queue: MemorySegment): Int
}

private class AppleAudioQueue : MacAudioQueueApi {
    private val linker = Linker.nativeLinker()
    private val library =
        SymbolLookup.libraryLookup(
            "/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox",
            Arena.global(),
        )

    private fun function(
        name: String,
        vararg arguments: MemoryLayout,
    ) = linker.downcallHandle(library.findOrThrow(name), FunctionDescriptor.of(JAVA_INT, *arguments))

    private val create = function("AudioQueueNewOutput", ADDRESS, ADDRESS, ADDRESS, ADDRESS, ADDRESS, JAVA_INT, ADDRESS)
    private val allocate = function("AudioQueueAllocateBuffer", ADDRESS, JAVA_INT, ADDRESS)
    private val enqueue = function("AudioQueueEnqueueBuffer", ADDRESS, ADDRESS, JAVA_INT, ADDRESS)
    private val start = function("AudioQueueStart", ADDRESS, ADDRESS)
    private val running = function("AudioQueueGetProperty", ADDRESS, JAVA_INT, ADDRESS, ADDRESS)
    private val reset = function("AudioQueueReset", ADDRESS)
    private val dispose = function("AudioQueueDispose", ADDRESS, JAVA_BYTE)

    override fun create(
        format: MemorySegment,
        callback: MemorySegment,
        result: MemorySegment,
    ): Int = create.invokeExact(format, callback, MemorySegment.NULL, MemorySegment.NULL, MemorySegment.NULL, 0, result) as Int

    override fun allocate(
        queue: MemorySegment,
        capacity: Int,
        result: MemorySegment,
    ): Int = allocate.invokeExact(queue, capacity, result) as Int

    override fun enqueue(
        queue: MemorySegment,
        buffer: MemorySegment,
    ): Int = enqueue.invokeExact(queue, buffer, 0, MemorySegment.NULL) as Int

    override fun start(queue: MemorySegment): Int = start.invokeExact(queue, MemorySegment.NULL) as Int

    override fun running(
        queue: MemorySegment,
        value: MemorySegment,
        size: MemorySegment,
    ): Int = running.invokeExact(queue, 0x6171726e, value, size) as Int // kAudioQueueProperty_IsRunning = 'aqrn'.

    override fun reset(queue: MemorySegment): Int = reset.invokeExact(queue) as Int

    override fun dispose(queue: MemorySegment): Int = dispose.invokeExact(queue, 1.toByte()) as Int
}
