package emberwood

import java.lang.foreign.Arena
import java.lang.foreign.Linker
import java.lang.foreign.MemorySegment
import java.lang.foreign.ValueLayout.ADDRESS
import java.lang.foreign.ValueLayout.JAVA_BYTE
import java.lang.foreign.ValueLayout.JAVA_DOUBLE
import java.lang.foreign.ValueLayout.JAVA_INT
import java.util.Collections
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import javax.sound.sampled.AudioFormat
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class MacAudioOutputTest {
    private val format = AudioFormat(22050f, 16, 1, true, false)

    @Test
    fun exactPcmUsesBoundedNativeBuffersAndReturnedBuffersOnly() {
        FakeQueue().use { api ->
            MacAudioOutput(api).use { output ->
                output.open(format, 4096)
                assertEquals(22050.0, api.stream!!.get(JAVA_DOUBLE, 0))
                assertEquals(listOf(0x6c70636d, 12, 2, 1, 2, 1, 16, 0), (8L..36L step 4).map { api.stream!!.get(JAVA_INT, it) })
                assertEquals(4096, api.allocatedBytes)
                assertTrue(output.isOpen)
                assertFalse(output.isRunning)
                output.start()
                assertTrue(output.isRunning)
                assertEquals(8, api.payloads.size)
                assertTrue(api.payloads.all { bytes -> bytes.all { it == 0.toByte() } })
                api.returnOne()
                val pcm = byteArrayOf(99, 0, 1, -1, 127, 0, -128, 99)
                assertEquals(6, output.write(pcm, 1, 6))
                assertContentEquals(pcm.copyOfRange(1, 7), api.payloads.last())
                assertEquals(8, api.queued.size)
            }
            assertEquals(1, api.disposals)
            assertFalse(api.callback!!.scope().isAlive)
        }
    }

    @Test
    fun resetReturnsBuffersWithoutDeadlockingAndDiscardsTheBlockedOldWrite() {
        FakeQueue().use { api ->
            MacAudioOutput(api).use { output ->
                output.open(format, 4096)
                output.start()
                Executors.newSingleThreadExecutor().use { executor ->
                    val entered = CountDownLatch(1)
                    val pending =
                        executor.submit<Int> {
                            entered.countDown()
                            output.write(ByteArray(512) { 67 }, 0, 512)
                        }
                    assertTrue(entered.await(1, TimeUnit.SECONDS))
                    Thread.sleep(60)
                    assertFalse(pending.isDone, "A full native queue must apply backpressure")
                    output.flush()
                    assertEquals(512, pending.get(1, TimeUnit.SECONDS))
                    assertEquals(8, api.payloads.size, "Reset must discard the pending pre-mute block")
                    assertEquals(512, output.write(ByteArray(512) { 12 }, 0, 512))
                    assertTrue(api.payloads.last().all { it == 12.toByte() })
                    assertEquals(1, api.queued.size)
                }
            }
        }
    }

    @Test
    fun closeReleasesAFullWriterAndKeepsCallbackAliveUntilSynchronousDisposalEnds() {
        FakeQueue().use { api ->
            val output = MacAudioOutput(api)
            output.open(format, 4096)
            output.start()
            api.disposeRelease = CountDownLatch(1)
            api.returnBeforeDisposeWait = true
            Executors.newFixedThreadPool(2).use { executor ->
                val writer = executor.submit<Int> { output.write(ByteArray(512), 0, 512) }
                Thread.sleep(60)
                assertFalse(writer.isDone)
                val closing = executor.submit { output.close() }
                try {
                    assertTrue(api.disposeEntered.await(1, TimeUnit.SECONDS))
                    assertEquals(0, writer.get(1, TimeUnit.SECONDS))
                    assertFalse(output.isRunning)
                    assertTrue(api.callback!!.scope().isAlive)
                    api.returnOne() // Real FFM callback while synchronous native disposal is blocked.
                } finally {
                    api.disposeRelease!!.countDown()
                }
                closing.get(1, TimeUnit.SECONDS)
            }
            output.close()
            assertEquals(1, api.disposals)
            assertFalse(api.callback!!.scope().isAlive)
        }
    }

    @Test
    fun closeWakesWriterEvenWhenResetIsStillInsideItsNativeCall() {
        FakeQueue().use { api ->
            val output = MacAudioOutput(api)
            output.open(format, 4096)
            output.start()
            api.resetRelease = CountDownLatch(1)
            Executors.newFixedThreadPool(3).use { executor ->
                val writer = executor.submit<Int> { output.write(ByteArray(512), 0, 512) }
                Thread.sleep(60)
                assertFalse(writer.isDone)
                val resetting = executor.submit { output.flush() }
                var closing: java.util.concurrent.Future<*>? = null
                try {
                    assertTrue(api.resetEntered.await(1, TimeUnit.SECONDS))
                    closing = executor.submit { output.close() }
                    assertEquals(0, writer.get(1, TimeUnit.SECONDS))
                    assertTrue(api.callback!!.scope().isAlive)
                } finally {
                    api.resetRelease!!.countDown()
                }
                resetting.get(1, TimeUnit.SECONDS)
                closing?.get(1, TimeUnit.SECONDS)
            }
            output.close()
            assertEquals(8, api.payloads.size)
            assertEquals(1, api.disposals)
            assertFalse(api.callback!!.scope().isAlive)
        }
    }

    @Test
    fun partialInitializationFailureDisposesTheQueueBeforeReleasingTheCallback() {
        FakeQueue().use { api ->
            api.failAllocation = 3
            val output = MacAudioOutput(api)
            val error = assertFailsWith<IllegalStateException> { output.open(format, 4096) }
            assertTrue(error.message!!.contains("AudioQueueAllocateBuffer failed with OSStatus -50"))
            assertFalse(output.isOpen)
            assertFalse(output.isRunning)
            assertEquals(1, api.disposals)
            assertFalse(api.callback!!.scope().isAlive)
            output.close()
            assertEquals(1, api.disposals)
        }
    }

    @Test
    fun callbackFailureIsReportedToTheWriterWithoutEscapingTheNativeCallback() {
        FakeQueue().use { api ->
            MacAudioOutput(api).use { output ->
                output.open(format, 4096)
                output.start()
                api.returnUnknown()
                val error = assertFailsWith<IllegalStateException> { output.write(ByteArray(2), 0, 2) }
                assertEquals("Audio playback callback failed", error.message)
                assertTrue(error.cause!!.message!!.contains("unknown buffer"))
            }
        }
    }

    @Test
    fun invalidFormatAndInactiveWritesFailWithoutNativeInitialization() {
        FakeQueue().use { api ->
            MacAudioOutput(api).use { output ->
                assertFailsWith<IllegalArgumentException> { output.open(AudioFormat(48000f, 16, 2, true, false), 4096) }
                assertFailsWith<IllegalArgumentException> { output.open(format, 8192) }
                assertFailsWith<IllegalStateException> { output.write(ByteArray(2), 0, 2) }
                assertEquals(0, api.allocatedBytes)
                assertEquals(null, api.callback)
            }
        }
    }

    internal class FakeQueue :
        MacAudioQueueApi,
        AutoCloseable {
        private val memory = Arena.ofShared()
        private val queue = memory.allocate(8)
        var callback: MemorySegment? = null
        var stream: MemorySegment? = null
        var allocatedBytes = 0
        var failAllocation = Int.MAX_VALUE
        var disposals = 0
        var disposeRelease: CountDownLatch? = null
        var returnBeforeDisposeWait = false
        var resetRelease: CountDownLatch? = null
        val disposeEntered = CountDownLatch(1)
        val resetEntered = CountDownLatch(1)
        val queued = ConcurrentLinkedQueue<MemorySegment>()
        val payloads = Collections.synchronizedList(mutableListOf<ByteArray>())
        private var started = false
        private var allocations = 0

        override fun create(
            format: MemorySegment,
            callback: MemorySegment,
            result: MemorySegment,
        ): Int {
            this.callback = callback
            stream = memory.allocate(MacAudioOutput.STREAM_LAYOUT).copyFrom(format)
            result.set(ADDRESS, 0, queue)
            return 0
        }

        override fun allocate(
            queue: MemorySegment,
            capacity: Int,
            result: MemorySegment,
        ): Int {
            if (++allocations == failAllocation) return -50
            val buffer = memory.allocate(MacAudioOutput.BUFFER_LAYOUT)
            buffer.set(JAVA_INT, 0, capacity)
            buffer.set(ADDRESS, 8, memory.allocate(capacity.toLong()))
            result.set(ADDRESS, 0, buffer)
            allocatedBytes += capacity
            return 0
        }

        override fun enqueue(
            queue: MemorySegment,
            buffer: MemorySegment,
        ): Int {
            check(queued.none { it.address() == buffer.address() }) { "Buffer enqueued twice without a callback" }
            queued.add(buffer)
            val data = buffer.get(ADDRESS, 8).reinterpret(buffer.get(JAVA_INT, 16).toLong())
            payloads.add(data.toArray(JAVA_BYTE))
            return 0
        }

        override fun start(queue: MemorySegment): Int {
            started = true
            return 0
        }

        override fun running(
            queue: MemorySegment,
            value: MemorySegment,
            size: MemorySegment,
        ): Int {
            value.set(JAVA_INT, 0, if (started) 1 else 0)
            return 0
        }

        override fun reset(queue: MemorySegment): Int {
            if (queued.isNotEmpty()) returnOne()
            resetEntered.countDown()
            check(resetRelease?.await(2, TimeUnit.SECONDS) != false) { "Test reset barrier was not released" }
            while (queued.isNotEmpty()) returnOne()
            return 0
        }

        fun returnOne() {
            val buffer = checkNotNull(queued.poll())
            invokeCallback(buffer)
        }

        fun returnUnknown() = invokeCallback(memory.allocate(8))

        private fun invokeCallback(buffer: MemorySegment) {
            Linker
                .nativeLinker()
                .downcallHandle(callback!!, MacAudioOutput.CALLBACK_DESCRIPTOR)
                .invokeWithArguments(MemorySegment.NULL, queue, buffer)
        }

        override fun dispose(queue: MemorySegment): Int {
            if (returnBeforeDisposeWait && queued.isNotEmpty()) returnOne()
            disposeEntered.countDown()
            check(disposeRelease?.await(2, TimeUnit.SECONDS) != false) { "Test disposal barrier was not released" }
            check(callback!!.scope().isAlive) { "Callback was released before native disposal" }
            reset(queue)
            started = false
            disposals++
            return 0
        }

        override fun close() = memory.close()
    }
}
