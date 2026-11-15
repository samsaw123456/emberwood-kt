package emberwood

import java.awt.Color
import java.awt.Graphics
import java.awt.image.BufferedImage

/** Test-only frame nonce: monochrome cells survive display color-profile conversion. */
internal object PresentationMarker {
    private const val ORIGIN = 8
    private const val CELL = 3
    private const val COLUMNS = 4
    private const val CELLS = 20

    fun paint(
        graphics: Graphics,
        nonce: Int,
    ) {
        require(nonce in 0..65535)
        repeat(CELLS) { index ->
            graphics.color = if (white(index, nonce)) Color.WHITE else Color.BLACK
            graphics.fillRect(ORIGIN + index % COLUMNS * CELL, ORIGIN + index / COLUMNS * CELL, CELL, CELL)
        }
    }

    fun matches(
        image: BufferedImage,
        nonce: Int,
    ): Boolean {
        require(nonce in 0..65535)
        if (image.width < ORIGIN + COLUMNS * CELL || image.height < ORIGIN + CELLS / COLUMNS * CELL) return false
        return (0 until CELLS).all { index ->
            val rgb = image.getRGB(ORIGIN + index % COLUMNS * CELL + 1, ORIGIN + index / COLUMNS * CELL + 1)
            val channels = listOf(rgb shr 16 and 255, rgb shr 8 and 255, rgb and 255)
            if (white(index, nonce)) channels.all { it >= 224 } else channels.all { it <= 31 }
        }
    }

    private fun white(
        index: Int,
        nonce: Int,
    ) = if (index < 4) index % 2 == 0 else nonce and (1 shl (index - 4)) != 0
}
