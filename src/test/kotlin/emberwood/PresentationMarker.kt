package emberwood

import java.awt.Color
import java.awt.Component
import java.awt.Graphics
import java.awt.image.BufferedImage
import javax.swing.border.AbstractBorder

/** Test-only frame nonce: monochrome cells survive display color-profile conversion. */
internal object PresentationMarker {
    private const val ORIGIN = 8
    private const val CELL = 3
    private const val COLUMNS = 4
    private const val CELLS = 20

    /** Paint after the actual game's component on every repaint, without changing its layout. */
    fun border(
        afterPaint: ((Int) -> Unit)? = null,
        nonce: () -> Int,
    ) = object : AbstractBorder() {
        override fun paintBorder(
            component: Component?,
            graphics: Graphics,
            x: Int,
            y: Int,
            width: Int,
            height: Int,
        ) {
            val overlay = graphics.create()
            try {
                overlay.translate(x, y)
                val paintedNonce = nonce()
                paint(overlay, paintedNonce)
                afterPaint?.invoke(paintedNonce)
            } finally {
                overlay.dispose()
            }
        }
    }

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
        return readNonce(image) == nonce
    }

    fun readNonce(image: BufferedImage): Int? {
        if (image.width < ORIGIN + COLUMNS * CELL || image.height < ORIGIN + CELLS / COLUMNS * CELL) return null
        var nonce = 0
        for (index in 0 until CELLS) {
            val rgb = image.getRGB(ORIGIN + index % COLUMNS * CELL + 1, ORIGIN + index / COLUMNS * CELL + 1)
            val channels = listOf(rgb shr 16 and 255, rgb shr 8 and 255, rgb and 255)
            val isWhite =
                when {
                    channels.all { it >= 224 } -> true
                    channels.all { it <= 31 } -> false
                    else -> return null
                }
            if (index < 4) {
                if (isWhite != (index % 2 == 0)) return null
            } else if (isWhite) {
                nonce = nonce or (1 shl (index - 4))
            }
        }
        return nonce
    }

    private fun white(
        index: Int,
        nonce: Int,
    ) = if (index < 4) index % 2 == 0 else nonce and (1 shl (index - 4)) != 0
}
