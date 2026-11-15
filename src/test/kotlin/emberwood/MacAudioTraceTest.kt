package emberwood

import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.SourceDataLine
import kotlin.io.path.deleteRecursively
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class MacAudioTraceTest {
    private val format = AudioFormat(22050f, 16, 1, true, false)

    @Test
    fun retainedGeneratedAndNativeSamplesStayExactWhileCallbacksReturnBuffers() =
        withDirectory { directory ->
            val trace = MacAudioTrace(directory, 128, 4096)
            val bytes = ByteArray(516) { (it % 119 + 1).toByte() }
            val expected = bytes.copyOfRange(2, 514)
            MacAudioOutputTest.FakeQueue().use { api ->
                val line = trace.line(MacAudioOutput(TracingMacQueue(api, trace)))
                line.open(format, 4096)
                line.start()
                api.returnOne()
                assertEquals(512, writeBounded(line, bytes, 2, 512))
                bytes.fill(0)
                assertContentEquals(expected, api.payloads.last())
                line.flush()
                line.close()
                assertFalse(api.callback!!.scope().isAlive)
            }
            trace.finish()
            val events = events(directory)
            val pcm = Files.readAllBytes(directory.resolve("samples.s16le"))
            val generated = events.single { it["Event"] == "generated" }
            val enqueued = events.last { it["Event"] == "enqueue" }
            for (event in listOf(generated, enqueued)) {
                val offset = event.getValue("PCM offset").toInt()
                assertContentEquals(expected, pcm.copyOfRange(offset, offset + event.getValue("Bytes").toInt()))
            }
            assertEquals(8, events.count { it["Event"] == "enqueue" && it["PCM offset"] == "-1" })
            assertEquals(9, events.count { it["Event"] == "callback" })
            assertEquals(8, events.maxOf { it.getValue("Pending buffers").toInt() })
            assertEquals("0", events.last().getValue("Pending buffers"))
            val summary = Files.readString(directory.resolve("summary.json"))
            assertTrue(summary.contains("\"result\": \"PASS\""))
            assertTrue(summary.contains("\"native_queue_disposed\": true"))
            assertEquals(2, Regex("nano_before").findAll(summary).count())
        }

    @Test
    fun traceOverflowFailsItsReceiptWithoutChangingNativeSamplesOrBlockingCallbacks() =
        withDirectory { directory ->
            val trace = MacAudioTrace(directory, 2, 1)
            MacAudioOutputTest.FakeQueue().use { api ->
                val line = trace.line(MacAudioOutput(TracingMacQueue(api, trace)))
                line.open(format, 4096)
                line.start()
                api.returnOne()
                val pcm = ByteArray(512) { 73 }
                assertEquals(512, writeBounded(line, pcm, 0, pcm.size))
                assertContentEquals(pcm, api.payloads.last())
                line.close()
            }
            trace.finish()
            val summary = Files.readString(directory.resolve("summary.json"))
            assertTrue(summary.contains("\"result\": \"FAIL\""))
            assertTrue(summary.contains("\"truncated\": true"))
            assertTrue(summary.contains("\"native_queue_disposed\": true"))
        }

    @Test
    fun forwardingCallbackRemainsAliveUntilSynchronousNativeDisposalCompletes() =
        withDirectory { directory ->
            val trace = MacAudioTrace(directory, 128, 4096)
            MacAudioOutputTest.FakeQueue().use { api ->
                val output = MacAudioOutput(TracingMacQueue(api, trace))
                output.open(format, 4096)
                output.start()
                api.disposeRelease = CountDownLatch(1)
                Executors.newSingleThreadExecutor().use { executor ->
                    val closing = executor.submit { output.close() }
                    try {
                        assertTrue(api.disposeEntered.await(1, TimeUnit.SECONDS))
                        assertTrue(api.callback!!.scope().isAlive)
                        api.returnOne()
                    } finally {
                        api.disposeRelease!!.countDown()
                    }
                    closing.get(2, TimeUnit.SECONDS)
                }
                assertFalse(api.callback!!.scope().isAlive)
            }
            trace.finish()
            assertTrue(Files.readString(directory.resolve("summary.json")).contains("\"result\": \"PASS\""))
        }

    private fun events(directory: Path): List<Map<String, String>> {
        val lines = Files.readAllLines(directory.resolve("events.tsv"))
        val headings = lines.first().split('\t')
        return lines.drop(1).map { headings.zip(it.split('\t')).toMap() }
    }

    private fun writeBounded(
        line: SourceDataLine,
        bytes: ByteArray,
        offset: Int,
        length: Int,
    ): Int =
        Executors.newSingleThreadExecutor().use { executor ->
            val written = executor.submit<Int> { line.write(bytes, offset, length) }
            try {
                written.get(2, TimeUnit.SECONDS)
            } finally {
                if (!written.isDone) {
                    line.close()
                    written.cancel(true)
                }
            }
        }

    @OptIn(kotlin.io.path.ExperimentalPathApi::class)
    private fun withDirectory(body: (Path) -> Unit) {
        val directory = Files.createTempDirectory("emberwood-native-audio-trace-")
        try {
            body(directory)
        } finally {
            directory.deleteRecursively()
        }
    }
}
