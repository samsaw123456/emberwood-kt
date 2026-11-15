package emberwood

import java.awt.Color
import java.awt.image.BufferedImage
import java.nio.file.Files
import javax.imageio.ImageIO
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class RejectedCapturesTest {
    @Test
    fun timedOutRequestCannotSupplyTheNextRequestsPresentationNonce() {
        val captures = RejectedCaptures()
        val failedRequest = captures.begin(7)
        val nextRequest = captures.begin(7)
        val image = BufferedImage(32, 32, BufferedImage.TYPE_INT_RGB)
        val graphics = image.createGraphics()
        try {
            PresentationMarker.paint(graphics, failedRequest.nonce)
        } finally {
            graphics.dispose()
        }
        assertEquals(failedRequest.sequence, nextRequest.sequence)
        assertTrue(PresentationMarker.matches(image, failedRequest.nonce))
        assertFalse(PresentationMarker.matches(image, nextRequest.nonce))

        repeat(65534) { captures.begin(7) }
        assertFailsWith<IllegalStateException> { captures.begin(7) }
    }

    @Test
    fun failedRequestsKeepDistinctOriginalsWhenAcceptedSequenceDoesNotAdvance() {
        val directory = Files.createTempDirectory("emberwood-rejected-captures-")
        try {
            val captures = RejectedCaptures()
            val first = captures.begin(7)
            val firstLatest = captures.retain(first, pixel(Color.RED))
            repeat(50) { captures.retain(first, pixel(Color.BLUE)) }
            captures.flush(directory)

            // A later case can fail before any accepted frame increments sequence 7.
            val second = captures.begin(7)
            val secondLatest = captures.retain(second, pixel(Color.GREEN))
            captures.retain(second, pixel(Color.YELLOW))
            captures.flush(directory)

            assertNotEquals(first.invocation, second.invocation)
            assertNotEquals(firstLatest, secondLatest)
            Files.list(directory).use { files -> assertEquals(4L, files.count()) }
            for ((name, color) in listOf(
                firstLatest.replace("-latest.png", "-first.png") to Color.RED,
                firstLatest to Color.BLUE,
                secondLatest.replace("-latest.png", "-first.png") to Color.GREEN,
                secondLatest to Color.YELLOW,
            )) {
                assertEquals(color.rgb, ImageIO.read(directory.resolve(name).toFile()).getRGB(0, 0), name)
            }
        } finally {
            directory.toFile().deleteRecursively()
        }
    }

    private fun pixel(color: Color) =
        BufferedImage(1, 1, BufferedImage.TYPE_INT_RGB).apply {
            setRGB(0, 0, color.rgb)
        }
}
