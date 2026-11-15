package emberwood

import java.awt.Dimension
import java.lang.foreign.Arena
import java.lang.foreign.FunctionDescriptor
import java.lang.foreign.Linker
import java.lang.foreign.MemorySegment
import java.lang.foreign.SymbolLookup
import java.lang.foreign.ValueLayout.ADDRESS
import java.lang.foreign.ValueLayout.JAVA_LONG
import java.nio.file.Files
import java.nio.file.Path
import javax.swing.JFrame
import javax.swing.JPanel
import javax.swing.SwingUtilities

/** Real AppKit ABI/menu-lifecycle proof; the external game audit separately checks input, appearance and Command-Q. */
object MacApplicationMenuProbe {
    @JvmStatic
    fun main(args: Array<String>) {
        require(args.size == 1) { "Supply a fresh output directory" }
        check(System.getProperty("os.name").startsWith("Mac")) { "The native menu probe requires macOS" }
        val output = Path.of(args[0]).toAbsolutePath()
        check(!Files.exists(output)) { "Preserve the earlier probe; use a fresh output directory" }
        Files.createDirectories(output)
        var frame: JFrame? = null
        var failure: Throwable? = null
        try {
            SwingUtilities.invokeAndWait {
                frame =
                    JFrame("Emberwood menu probe").apply {
                        contentPane = JPanel().apply { preferredSize = Dimension(800, 600) }
                        pack()
                    }
            }
            val api = CocoaMenuApi()
            val inspector = Inspector(api)
            val before = inspector.snapshot()
            check(before.services != 0L) { "Fresh AWT startup supplied no Services menu; removal was not exercised" }
            before.write(output.resolve("menu-before.tsv"))
            val expected = before.items.filter { it.submenu != before.services }
            check(expected.size == before.items.size - 1) { "Registered Services submenu must identify exactly one native item" }
            check(expected.any { it.actionName == "terminate:" }) { "The default native Quit action is absent" }
            SwingUtilities.invokeAndWait { MacApplicationMenu.configure() }
            val prepared = inspector.snapshot()
            prepared.write(output.resolve("menu-prepared.tsv"))
            check(prepared.services == 0L && prepared.items == expected) { "Preparation changed a sibling or retained Services" }
            SwingUtilities.invokeAndWait { checkNotNull(frame).isVisible = true }
            val shown = inspector.snapshot()
            shown.write(output.resolve("menu-shown.tsv"))
            check(shown.services == 0L && shown.items == expected) { "Showing the window restored Services or changed another native item" }
            api.onMainThread {
                check(!MacApplicationMenu.removeServices(api)) { "Idempotent direct-main-thread configuration changed another item" }
            }
            check(inspector.snapshot() == shown)
        } catch (error: Throwable) {
            failure = error
        } finally {
            try {
                SwingUtilities.invokeAndWait { frame?.dispose() }
            } catch (cleanup: Throwable) {
                if (failure == null) failure = cleanup else failure.addSuppressed(cleanup)
            }
        }
        val error = failure
        Files.writeString(
            output.resolve("result.json"),
            if (error == null) {
                "{\"result\":\"PASS\",\"services_absent_after_show\":true,\"sibling_identities_actions_preserved\":true," +
                    "\"direct_main_thread_idempotence\":true,\"owned_window_disposed\":true}\n"
            } else {
                "{\"result\":\"FAIL\",\"error\":\"${error.toString().replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")}\"}\n"
            },
        )
        if (error != null) throw error
        println("PASS: exact Services removal, unchanged sibling identities/actions, post-show persistence and direct AppKit idempotence")
    }

    private data class Item(
        val identity: Long,
        val title: String,
        val submenu: Long,
        val action: Long,
        val actionName: String,
        val target: Long,
        val key: String,
        val modifiers: Long,
    )

    private data class Snapshot(
        val services: Long,
        val items: List<Item>,
    ) {
        fun write(path: Path) {
            Files.writeString(
                path,
                "identity\ttitle\tsubmenu\taction\taction_name\ttarget\tkey\tmodifiers\n" +
                    items.joinToString("\n", postfix = "\n") {
                        listOf(it.identity, it.title, it.submenu, it.action, it.actionName, it.target, it.key, it.modifiers)
                            .joinToString("\t") { value -> value.toString().replace("\t", " ").replace("\n", " ") }
                    },
            )
        }
    }

    /** Independent read-only inspection of original native identities, selectors and shortcuts. */
    private class Inspector(
        private val api: CocoaMenuApi,
    ) {
        private val linker = Linker.nativeLinker()
        private val objc = SymbolLookup.libraryLookup("/usr/lib/libobjc.A.dylib", Arena.global())
        private val message = objc.findOrThrow("objc_msgSend")
        private val pointer = linker.downcallHandle(message, FunctionDescriptor.of(ADDRESS, ADDRESS, ADDRESS))
        private val pointerAt = linker.downcallHandle(message, FunctionDescriptor.of(ADDRESS, ADDRESS, ADDRESS, JAVA_LONG))
        private val integer = linker.downcallHandle(message, FunctionDescriptor.of(JAVA_LONG, ADDRESS, ADDRESS))
        private val register = linker.downcallHandle(objc.findOrThrow("sel_registerName"), FunctionDescriptor.of(ADDRESS, ADDRESS))
        private val selectorName = linker.downcallHandle(objc.findOrThrow("sel_getName"), FunctionDescriptor.of(ADDRESS, ADDRESS))

        fun snapshot(): Snapshot {
            var result: Snapshot? = null
            api.onMainThread {
                val app = api.application()
                val main = pointer(app, "mainMenu")
                val applicationItem = pointerAt.invokeExact(main, selector("itemAtIndex:"), 0L) as MemorySegment
                val menu = pointer(applicationItem, "submenu")
                val count = integer.invokeExact(menu, selector("numberOfItems")) as Long
                check(count in 1..100) { "Unexpected native application menu size $count" }
                result =
                    Snapshot(
                        api.servicesMenu(app).address(),
                        (0 until count).map { index ->
                            val item = pointerAt.invokeExact(menu, selector("itemAtIndex:"), index) as MemorySegment
                            val action = pointer(item, "action")
                            Item(
                                item.address(),
                                string(pointer(item, "title")),
                                pointer(item, "submenu").address(),
                                action.address(),
                                if (action == MemorySegment.NULL) "" else cString(selectorName.invokeExact(action) as MemorySegment),
                                pointer(item, "target").address(),
                                string(pointer(item, "keyEquivalent")),
                                integer.invokeExact(item, selector("keyEquivalentModifierMask")) as Long,
                            )
                        },
                    )
            }
            return checkNotNull(result)
        }

        private fun pointer(
            receiver: MemorySegment,
            name: String,
        ): MemorySegment = pointer.invokeExact(receiver, selector(name)) as MemorySegment

        private fun string(value: MemorySegment): String = if (value == MemorySegment.NULL) "" else cString(pointer(value, "UTF8String"))

        private fun cString(value: MemorySegment): String = if (value == MemorySegment.NULL) "" else value.reinterpret(4096).getString(0)

        private fun selector(name: String): MemorySegment =
            Arena.ofConfined().use { arena ->
                register.invokeExact(arena.allocateFrom(name)) as MemorySegment
            }
    }
}
