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
        val observe = args.size == 2 && args[0] == "--observe-registration"
        require(args.size == 1 || observe) { "Supply [--observe-registration] and a fresh output directory" }
        check(System.getProperty("os.name").startsWith("Mac")) { "The native menu probe requires macOS" }
        val output = Path.of(args.last()).toAbsolutePath()
        check(!Files.exists(output)) { "Preserve the earlier probe; use a fresh output directory" }
        Files.createDirectories(output)
        var frame: JFrame? = null
        var failure: Throwable? = null
        val observations = mutableListOf<String>()
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
            if (observe) {
                observeRegistration(output, checkNotNull(frame), api, inspector, observations)
            } else {
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
                check(
                    shown.services == 0L && shown.items == expected,
                ) { "Showing the window restored Services or changed another native item" }
                api.onMainThread {
                    check(!MacApplicationMenu.removeServices(api)) { "Idempotent direct-main-thread configuration changed another item" }
                }
                check(inspector.snapshot() == shown)
            }
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
        val details =
            "\"mode\":\"${if (observe) "observe-registration" else "strict"}\",\"gameplay_verified\":false," +
                "\"observations\":[${observations.joinToString(",")}]"
        Files.writeString(
            output.resolve("result.json"),
            if (error == null && observe) {
                "{\"result\":\"OBSERVATION_COMPLETE\",\"owned_window_disposed\":true,$details}\n"
            } else if (error == null) {
                "{\"result\":\"PASS\",\"services_absent_after_show\":true,\"sibling_identities_actions_preserved\":true," +
                    "\"direct_main_thread_idempotence\":true,\"owned_window_disposed\":true,$details}\n"
            } else {
                val message =
                    error
                        .toString()
                        .replace("\\", "\\\\")
                        .replace("\"", "\\\"")
                        .replace("\n", "\\n")
                "{\"result\":\"FAIL\",\"error\":\"$message\",$details}\n"
            },
        )
        if (error != null) throw error
        if (observe) {
            println("OBSERVATION_COMPLETE: native Services registration lifecycle recorded; no game verification or input")
        } else {
            println(
                "PASS: exact Services removal, unchanged sibling identities/actions, post-show persistence and direct AppKit idempotence",
            )
        }
    }

    private fun observeRegistration(
        output: Path,
        frame: JFrame,
        api: CocoaMenuApi,
        inspector: Inspector,
        observations: MutableList<String>,
    ) {
        var originalServices = 0L

        fun record(phase: String): Snapshot {
            val state = inspector.snapshot()
            if (phase == "original") originalServices = state.services
            val filename = "menu-$phase.tsv"
            state.write(output.resolve(filename))
            val originalIndex = if (originalServices == 0L) -1 else state.items.indexOfFirst { it.submenu == originalServices }
            observations +=
                "{\"phase\":\"$phase\",\"services_pointer\":${state.services}," +
                "\"services_parent_pointer\":${state.servicesParent},\"services_parent_index\":${state.servicesIndex}," +
                "\"application_menu_pointer\":${state.applicationMenu}," +
                "\"original_services_item_index\":$originalIndex," +
                "\"items_tsv\":\"$filename\"}"
            return state
        }
        api.onMainThread {
            val original = record("original")
            check(original.services != 0L && original.servicesParent != 0L && original.servicesIndex != null) {
                "Fresh native Services menu is not attached; removal was not exercised"
            }
            check(original.servicesIndex >= 0) { "Services parent has no corresponding submenu item" }
            api.removeItem(MemorySegment.ofAddress(original.servicesParent), original.servicesIndex)
            record("after-removal")
            api.clearServicesMenu(api.application())
            record("after-set-first")
            record("after-set-second")
        }
        SwingUtilities.invokeAndWait { frame.isVisible = true }
        record("after-show")
        // Stored addresses are observations only: an old Services object may have been released by the setter.
        // Only the currently registered menu is queried; no Services child item is enumerated.
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
        val servicesParent: Long,
        val servicesIndex: Long?,
        val applicationMenu: Long,
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
                val services = api.servicesMenu(app)
                val parent = if (services == MemorySegment.NULL) MemorySegment.NULL else api.supermenu(services)
                result =
                    Snapshot(
                        services.address(),
                        parent.address(),
                        if (parent == MemorySegment.NULL) null else api.indexOfSubmenu(parent, services),
                        menu.address(),
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
