package emberwood

import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class NativeInputGateTest {
    @Test
    fun unresolvedAudioStopsBeforeNativeInput() {
        val opening = CountDownLatch(1)
        val allowFinish = CountDownLatch(1)
        val output = Files.createTempDirectory("emberwood-input-gate-pending-")
        val audio =
            Audio {
                opening.countDown()
                check(allowFinish.await(5, TimeUnit.SECONDS))
                error("Test provider released")
            }
        try {
            assertTrue(opening.await(2, TimeUnit.SECONDS))
            val error = assertFailsWith<IllegalStateException> { NativeInputGate.awaitAudioResolution(audio, output, 25) }
            assertTrue(error.message.orEmpty().contains("no input was sent"))
            assertTrue(Files.readString(output.resolve("input-startup-gate.txt")).contains("Audio: pending"))
        } finally {
            allowFinish.countDown()
            audio.close()
            output.toFile().deleteRecursively()
        }
    }

    @Test
    fun explicitAudioFailureIsRecordedAndDoesNotMasqueradeAsPending() {
        val output = Files.createTempDirectory("emberwood-input-gate-unavailable-")
        val audio = Audio { error("Output initialization failed") }
        try {
            assertEquals("unavailable: Output initialization failed", NativeInputGate.awaitAudioResolution(audio, output, 2_000))
            assertTrue(Files.readString(output.resolve("input-startup-gate.txt")).contains("unavailable: Output initialization failed"))
        } finally {
            audio.close()
            output.toFile().deleteRecursively()
        }
    }
}
