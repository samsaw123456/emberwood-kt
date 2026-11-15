package emberwood

import java.awt.Color
import java.awt.image.BufferedImage
import javax.imageio.ImageIO
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class PresentationMarkerTest {
    @Test
    fun intelCapturedColorShiftCannotRejectMonochromeFrameNonce() {
        val captured = ImageIO.read(checkNotNull(javaClass.getResource("/native-audit/intel-presentation-marker.png")))
        // Actual Intel capture of the old RGB(251,1,4) marker, not generated test pixels.
        val observed = Color(captured.getRGB(10, 10))
        assertEquals(Color(250, 3, 1), observed)
        assertNotEquals(Color(251, 1, 4), observed)
        assertFalse(PresentationMarker.matches(captured, 0))

        val current = frame(513)
        // Apply the independently observed channel shifts to the replacement marker.
        for (y in 0 until current.height) {
            for (x in 0 until current.width) {
                val color = Color(current.getRGB(x, y))
                current.setRGB(
                    x,
                    y,
                    Color((color.red - 1).coerceAtLeast(0), (color.green + 2).coerceAtMost(255), (color.blue - 3).coerceAtLeast(0)).rgb,
                )
            }
        }
        assertTrue(PresentationMarker.matches(current, 513))
        assertFalse(PresentationMarker.matches(current, 512))
    }

    @Test
    fun staleFramesAmbiguousCellsAndMissingAnchorsAreRejected() {
        for (nonce in 0..1300) {
            val image = frame(nonce)
            assertTrue(PresentationMarker.matches(image, nonce))
            assertFalse(PresentationMarker.matches(image, if (nonce == 0) 65535 else nonce - 1))
        }
        val ambiguous = frame(250)
        ambiguous.setRGB(9, 12, Color(128, 128, 128).rgb)
        assertFalse(PresentationMarker.matches(ambiguous, 250))
        assertFalse(PresentationMarker.matches(BufferedImage(32, 32, BufferedImage.TYPE_INT_RGB), 0))
        assertFalse(PresentationMarker.matches(BufferedImage(12, 12, BufferedImage.TYPE_INT_RGB), 0))
    }

    private fun frame(nonce: Int): BufferedImage {
        val image = BufferedImage(32, 32, BufferedImage.TYPE_INT_RGB)
        val graphics = image.createGraphics()
        try {
            graphics.color = Color(80, 90, 100)
            graphics.fillRect(0, 0, image.width, image.height)
            PresentationMarker.paint(graphics, nonce)
        } finally {
            graphics.dispose()
        }
        return image
    }
}
