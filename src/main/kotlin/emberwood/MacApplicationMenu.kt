package emberwood

import java.lang.foreign.Arena
import java.lang.foreign.FunctionDescriptor
import java.lang.foreign.Linker
import java.lang.foreign.MemorySegment
import java.lang.foreign.SymbolLookup
import java.lang.foreign.ValueLayout.ADDRESS
import java.lang.foreign.ValueLayout.JAVA_INT
import java.lang.foreign.ValueLayout.JAVA_LONG
import java.lang.invoke.MethodHandles
import java.lang.invoke.MethodType
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/** This command-only game has no selection to send to macOS Services. */
internal object MacApplicationMenu {
    fun configure() {
        // Do not load Cocoa symbols on another platform, including headless test machines.
        if (System.getProperty("os.name").startsWith("Mac")) removeServices(CocoaMenuApi())
    }

    internal fun removeServices(api: MacMenuApi): Boolean {
        var removed = false
        api.onMainThread {
            val application = api.application()
            check(application != MemorySegment.NULL) { "macOS application is not initialized" }
            val services = api.servicesMenu(application)
            if (services != MemorySegment.NULL) {
                val parent = api.supermenu(services)
                if (parent != MemorySegment.NULL) {
                    val index = api.indexOfSubmenu(parent, services)
                    check(index >= 0) { "macOS Services menu is missing from its parent" }
                    // NSApplication's strong servicesMenu property keeps the submenu alive after item removal.
                    api.removeItem(parent, index)
                    check(api.indexOfSubmenu(parent, services) == -1L) { "macOS Services menu was not removed" }
                    check(api.supermenu(services) == MemorySegment.NULL) { "macOS Services menu is still attached" }
                    removed = true
                }
                // NSApplication retains its registered submenu. Detaching that exact item prevents
                // irrelevant Services shortcut traversal without changing registration or sibling actions.
            }
        }
        return removed
    }
}

internal interface MacMenuApi {
    fun onMainThread(action: () -> Unit)

    fun application(): MemorySegment

    fun servicesMenu(application: MemorySegment): MemorySegment

    fun supermenu(menu: MemorySegment): MemorySegment

    fun indexOfSubmenu(
        menu: MemorySegment,
        submenu: MemorySegment,
    ): Long

    fun removeItem(
        menu: MemorySegment,
        index: Long,
    )
}

/** A synchronous callback cannot outlive its arena or unwind an exception through C. */
internal class AppKitMenuTask(
    private val action: () -> Unit,
) {
    private val completed = AtomicBoolean()
    private val failure = AtomicReference<Throwable>()

    fun dispatch(send: (MemorySegment) -> Unit) {
        Arena.ofShared().use { arena ->
            val method =
                MethodHandles
                    .lookup()
                    .findVirtual(
                        AppKitMenuTask::class.java,
                        "invoke",
                        MethodType.methodType(Void.TYPE, MemorySegment::class.java),
                    ).bindTo(this)
            val callback = Linker.nativeLinker().upcallStub(method, DESCRIPTOR, arena)
            send(callback)
            check(completed.get()) { "macOS application-menu callback did not complete" }
            failure.get()?.let { throw IllegalStateException("Unable to prepare the macOS application menu", it) }
        }
    }

    @Suppress("UNUSED_PARAMETER")
    private fun invoke(context: MemorySegment) {
        try {
            action()
        } catch (error: Throwable) {
            failure.set(error)
        } finally {
            completed.set(true)
        }
    }

    companion object {
        val DESCRIPTOR: FunctionDescriptor = FunctionDescriptor.ofVoid(ADDRESS)
    }
}

internal class CocoaMenuApi : MacMenuApi {
    private val linker = Linker.nativeLinker()
    private val objc = SymbolLookup.libraryLookup("/usr/lib/libobjc.A.dylib", Arena.global())
    private val system = SymbolLookup.libraryLookup("/usr/lib/libSystem.B.dylib", Arena.global())
    private val getClass = linker.downcallHandle(objc.findOrThrow("objc_getClass"), FunctionDescriptor.of(ADDRESS, ADDRESS))
    private val getSelector = linker.downcallHandle(objc.findOrThrow("sel_registerName"), FunctionDescriptor.of(ADDRESS, ADDRESS))
    private val message = objc.findOrThrow("objc_msgSend")

    // Each Objective-C call has its method's fixed signature, including on ARM64; it is not a C varargs call.
    private val pointer = linker.downcallHandle(message, FunctionDescriptor.of(ADDRESS, ADDRESS, ADDRESS))
    private val index = linker.downcallHandle(message, FunctionDescriptor.of(JAVA_LONG, ADDRESS, ADDRESS, ADDRESS))
    private val remove = linker.downcallHandle(message, FunctionDescriptor.ofVoid(ADDRESS, ADDRESS, JAVA_LONG))
    private val isMain = linker.downcallHandle(system.findOrThrow("pthread_main_np"), FunctionDescriptor.of(JAVA_INT))
    private val dispatch =
        linker.downcallHandle(system.findOrThrow("dispatch_sync_f"), FunctionDescriptor.ofVoid(ADDRESS, ADDRESS, ADDRESS))

    // Public dispatch/queue.h implements dispatch_get_main_queue() as the address of this exported object.
    // It is the queue itself, not a pointer slot, and must not be dereferenced.
    private val mainQueue = system.findOrThrow("_dispatch_main_q")
    private val applicationClass = classNamed("NSApplication")
    private val sharedApplication = selector("sharedApplication")
    private val services = selector("servicesMenu")
    private val parent = selector("supermenu")
    private val indexOf = selector("indexOfItemWithSubmenu:")
    private val removeAt = selector("removeItemAtIndex:")

    override fun onMainThread(action: () -> Unit) {
        if (isMain.invokeExact() as Int != 0) {
            action() // Dispatching synchronously to this same serial queue would deadlock.
        } else {
            AppKitMenuTask {
                check(isMain.invokeExact() as Int != 0) { "macOS menu work did not reach the main thread" }
                action()
            }.dispatch(::sendToMain)
        }
    }

    private fun sendToMain(callback: MemorySegment) {
        dispatch.invokeExact(mainQueue, MemorySegment.NULL, callback)
    }

    override fun application(): MemorySegment = pointer.invokeExact(applicationClass, sharedApplication) as MemorySegment

    override fun servicesMenu(application: MemorySegment): MemorySegment = pointer.invokeExact(application, services) as MemorySegment

    override fun supermenu(menu: MemorySegment): MemorySegment = pointer.invokeExact(menu, parent) as MemorySegment

    override fun indexOfSubmenu(
        menu: MemorySegment,
        submenu: MemorySegment,
    ): Long = index.invokeExact(menu, indexOf, submenu) as Long

    override fun removeItem(
        menu: MemorySegment,
        index: Long,
    ) {
        remove.invokeExact(menu, removeAt, index)
    }

    private fun classNamed(name: String): MemorySegment =
        Arena.ofConfined().use { arena ->
            (getClass.invokeExact(arena.allocateFrom(name)) as MemorySegment).also {
                check(it != MemorySegment.NULL) { "macOS class $name is unavailable; initialize AWT first" }
            }
        }

    private fun selector(name: String): MemorySegment =
        Arena.ofConfined().use { arena ->
            getSelector.invokeExact(arena.allocateFrom(name)) as MemorySegment
        }
}
