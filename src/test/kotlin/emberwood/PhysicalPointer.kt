package emberwood

import java.awt.Robot
import java.awt.event.InputEvent

/** Native app tests keep pointer privileges in the external controller; local audits retain Robot. */
internal class PhysicalPointer(
    private val robot: Robot?,
) : AutoCloseable {
    private val session = if (NativeAuditTools.hasExternalController) NativeAuditTools.BridgeSession("pointer-serve") else null
    private val held = linkedSetOf<Int>()

    fun move(
        x: Int,
        y: Int,
    ) {
        if (session != null) request("[\"move\",$x,$y]") else checkNotNull(robot).mouseMove(x, y)
    }

    fun button(
        mask: Int,
        down: Boolean,
    ) {
        val name = checkNotNull(buttons[mask]) { "Unsupported pointer button: $mask" }
        if (down) held.add(mask)
        if (session != null) {
            request("[\"button\",${NativeAuditTools.quote(name)},$down]")
        } else if (down) {
            checkNotNull(robot).mousePress(mask)
        } else {
            checkNotNull(robot).mouseRelease(mask)
        }
        if (!down) held.remove(mask)
    }

    fun wheel(rotation: Int) {
        if (session != null) {
            request("[\"wheel\",$rotation]")
        } else {
            // Quartz wheel-positive means up; Java's public wheel rotation is down-positive.
            checkNotNull(robot).mouseWheel(if (System.getProperty("os.name").startsWith("Mac")) -rotation else rotation)
        }
    }

    fun registerAuxiliary(title: String) {
        if (session != null) request("[\"register-aux\",${NativeAuditTools.quote(title)}]")
    }

    fun unregisterAuxiliary(title: String) {
        if (session != null) request("[\"unregister-aux\",${NativeAuditTools.quote(title)}]")
    }

    private fun request(message: String) {
        val reply = checkNotNull(session).request(message)
        check(reply == "OK") { "External pointer operation failed: $reply" }
    }

    fun releaseAll() {
        var failure: Throwable? = null
        for (mask in held.toList()) {
            try {
                button(mask, false)
            } catch (error: Throwable) {
                val previous = failure
                if (previous == null) failure = error else previous.addSuppressed(error)
            }
        }
        failure?.let { throw it }
    }

    override fun close() {
        var failure: Throwable? = null
        try {
            releaseAll()
        } catch (error: Throwable) {
            failure = error
        }
        try {
            session?.close()
        } catch (error: Throwable) {
            val previous = failure
            if (previous == null) failure = error else previous.addSuppressed(error)
        }
        failure?.let { throw it }
    }

    companion object {
        private val buttons =
            mapOf(
                InputEvent.BUTTON1_DOWN_MASK to "left",
                InputEvent.BUTTON2_DOWN_MASK to "middle",
                InputEvent.BUTTON3_DOWN_MASK to "right",
            )
    }
}
