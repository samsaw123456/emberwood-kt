package emberwood

import java.awt.image.BufferedImage
import kotlin.math.abs

/** Locate the visible original fox palette, including a fox at either viewport edge. */
internal object FoxPixels {
    fun center(image: BufferedImage): Pair<Double, Double> {
        var xTotal = 0.0
        var yTotal = 0.0
        var count = 0
        for (y in 170 until minOf(538, image.height)) {
            for (x in 0 until image.width) {
                val rgb = image.getRGB(x, y)
                if (abs((rgb shr 16 and 255) - 181) <= 1 &&
                    abs((rgb shr 8 and 255) - 66) <= 1 &&
                    abs((rgb and 255) - 45) <= 1
                ) {
                    xTotal += x
                    yTotal += y
                    count++
                }
            }
        }
        check(count > 10) { "Fox's original orange pixels were not visible ($count)" }
        return xTotal / count to yTotal / count
    }
}
