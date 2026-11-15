package emberwood

import java.nio.file.Path

/** LaunchServices can start an audit app outside the checkout and with a minimal PATH. */
internal object NativeAuditTools {
    fun python(vararg arguments: String): ProcessBuilder =
        ProcessBuilder(listOf(System.getProperty("audit.python", "python3")) + arguments)
            .directory(Path.of(System.getProperty("audit.root", ".")).toAbsolutePath().toFile())
}
