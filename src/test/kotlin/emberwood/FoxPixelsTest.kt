package emberwood

import java.awt.image.BufferedImage
import javax.imageio.ImageIO
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class FoxPixelsTest {
    @Test
    fun actualIntelBoundaryFrameKeepsItsVisibleFox() {
        val image = ImageIO.read(checkNotNull(javaClass.getResource("/native-audit/intel-fox-left-edge.png")))
        val center = FoxPixels.center(image)
        assertEquals(12.981012658227849, center.first, 0.001)
        assertTrue(center.second in 490.0..535.0)

        // The same visible pixels at the opposite viewport edge must remain observable too.
        val mirrored = BufferedImage(image.width, image.height, BufferedImage.TYPE_INT_RGB)
        for (y in 0 until image.height) {
            for (x in 0 until image.width) mirrored.setRGB(image.width - x - 1, y, image.getRGB(x, y))
        }
        assertEquals(image.width - 1 - center.first, FoxPixels.center(mirrored).first, 0.001)
    }

    @Test
    fun nonFoxColorsAndOffStagePixelsDoNotBecomeAFox() {
        val image = BufferedImage(1152, 648, BufferedImage.TYPE_INT_RGB)
        // A matching HUD color outside the gameplay band must not satisfy the observer.
        for (x in 0..100) image.setRGB(x, 100, 0xb5422d)
        assertFailsWith<IllegalStateException> { FoxPixels.center(image) }
        for (x in 0..100) image.setRGB(x, 500, 0xb5452d)
        assertFailsWith<IllegalStateException> { FoxPixels.center(image) }
    }
}
