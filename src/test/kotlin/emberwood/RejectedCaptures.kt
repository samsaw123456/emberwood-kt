package emberwood

import java.awt.image.BufferedImage
import java.nio.file.Path
import javax.imageio.ImageIO

/** Keep first/latest rejects per request, even when no accepted frame advances its sequence. */
internal class RejectedCaptures {
    data class Attempt(
        val sequence: Int,
        val invocation: Int,
    ) {
        val nonce: Int get() = invocation
    }

    private var nextInvocation = 0
    private val pending = linkedMapOf<String, BufferedImage>()

    fun begin(sequence: Int): Attempt {
        check(nextInvocation <= 65535) { "The 16-bit presentation nonce space is exhausted" }
        return Attempt(sequence, nextInvocation++)
    }

    fun retain(
        attempt: Attempt,
        image: BufferedImage,
    ): String {
        val prefix = "rejected-%04d-%04d".format(attempt.sequence, attempt.invocation)
        pending.putIfAbsent("$prefix-first.png", image)
        val latest = "$prefix-latest.png"
        pending[latest] = image
        return latest
    }

    fun flush(output: Path) {
        for ((name, image) in pending) check(ImageIO.write(image, "png", output.resolve(name).toFile()))
        pending.clear()
    }
}
