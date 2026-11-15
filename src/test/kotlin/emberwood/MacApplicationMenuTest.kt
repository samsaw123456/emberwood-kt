package emberwood

import java.lang.foreign.Linker
import java.lang.foreign.MemorySegment
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue

class MacApplicationMenuTest {
    @Test
    fun removesOnlyTheRegisteredSubmenuAndPreservesOtherItems() {
        val api = MenuFixture()
        val registered = api.registered
        val expected = api.items.filter { it.submenu != api.registered }
        assertTrue(MacApplicationMenu.removeServices(api))
        assertEquals(expected, api.items, "About, Hide, Quit and an identically named unrelated submenu must survive")
        expected.zip(api.items).forEach { (before, after) -> assertSame(before, after) }
        assertEquals(registered, api.registered, "Native registration may retain the detached submenu")
        assertEquals(MemorySegment.NULL, api.parent)
        assertEquals(listOf("remove:2"), api.changes)
        assertFalse(MacApplicationMenu.removeServices(api), "Repeated configuration must not remove a neighboring item")
        assertEquals(expected, api.items)
        assertEquals(listOf("remove:2"), api.changes)
    }

    @Test
    fun absentAndDetachedServicesDoNotRemoveAnyOtherMenuItem() {
        val absent = MenuFixture().also { it.registered = MemorySegment.NULL }
        val before = absent.items.toList()
        assertFalse(MacApplicationMenu.removeServices(absent))
        assertEquals(before, absent.items)
        assertTrue(absent.changes.isEmpty())
        val detached =
            MenuFixture().also {
                it.items.removeAll { item -> item.submenu == it.registered }
                it.parent = MemorySegment.NULL
            }
        val detachedBefore = detached.items.toList()
        val registered = detached.registered
        assertFalse(MacApplicationMenu.removeServices(detached))
        assertEquals(detachedBefore, detached.items)
        assertEquals(registered, detached.registered)
        assertTrue(detached.changes.isEmpty())
    }

    @Test
    fun inconsistentParentOrUninitializedApplicationFailsBeforeMutation() {
        for (api in listOf(MenuFixture().also { it.missingIndex = true }, MenuFixture().also { it.app = MemorySegment.NULL })) {
            val before = api.items.toList()
            assertFailsWith<IllegalStateException> { MacApplicationMenu.removeServices(api) }
            assertEquals(before, api.items)
            assertTrue(api.changes.isEmpty())
        }
    }

    @Test
    fun ineffectiveNativeMutationCannotReportSuccess() {
        val retainedItem = MenuFixture().also { it.ignoreRemove = true }
        assertFailsWith<IllegalStateException> { MacApplicationMenu.removeServices(retainedItem) }
        assertEquals(listOf("remove:2"), retainedItem.changes)
        val retainedParent = MenuFixture().also { it.ignoreDetach = true }
        assertFailsWith<IllegalStateException> { MacApplicationMenu.removeServices(retainedParent) }
        assertEquals(listOf("remove:2"), retainedParent.changes)
    }

    @Test
    fun nativeCallbackCanRunOnAnotherThreadAndItsArenaClosesAfterReturn() {
        val caller = Thread.currentThread()
        var callbackThread: Thread? = null
        var pointer: MemorySegment? = null
        AppKitMenuTask { callbackThread = Thread.currentThread() }.dispatch { callback ->
            pointer = callback
            invokeOnWorker(callback)
            assertTrue(callback.scope().isAlive)
        }
        assertTrue(callbackThread != null && callbackThread !== caller)
        assertFalse(checkNotNull(pointer).scope().isAlive)
    }

    @Test
    fun callbackErrorsReturnThroughCBeforeTheyAreRethrown() {
        val original = AssertionError("menu mutation failed")
        var returnedThroughC = false
        var pointer: MemorySegment? = null
        val failure =
            assertFailsWith<IllegalStateException> {
                AppKitMenuTask { throw original }.dispatch { callback ->
                    pointer = callback
                    invokeOnWorker(callback)
                    returnedThroughC = true
                }
            }
        assertTrue(returnedThroughC, "No Throwable may escape the native upcall")
        assertSame(original, failure.cause)
        assertFalse(checkNotNull(pointer).scope().isAlive)
    }

    @Test
    fun dispatchWithoutCompletedCallbackCannotSucceed() {
        assertFailsWith<IllegalStateException> { AppKitMenuTask { error("not invoked") }.dispatch {} }
    }

    private fun invokeOnWorker(callback: MemorySegment) {
        val failure = AtomicReference<Throwable>()
        Executors.newSingleThreadExecutor().use { executor ->
            executor
                .submit {
                    try {
                        invokeNative(callback)
                    } catch (error: Throwable) {
                        failure.set(error)
                    }
                }.get(2, TimeUnit.SECONDS)
        }
        failure.get()?.let { throw it }
    }

    private fun invokeNative(callback: MemorySegment) {
        val call = Linker.nativeLinker().downcallHandle(callback, AppKitMenuTask.DESCRIPTOR)
        call.invokeExact(MemorySegment.NULL)
    }

    private data class Item(
        val title: String,
        val action: String,
        val submenu: MemorySegment = MemorySegment.NULL,
    )

    private class MenuFixture : MacMenuApi {
        var app = MemorySegment.ofAddress(1)
        var registered = MemorySegment.ofAddress(2)
        private val container = MemorySegment.ofAddress(3)
        var parent = container
        var missingIndex = false
        var ignoreRemove = false
        var ignoreDetach = false
        var onMain = false
        val changes = mutableListOf<String>()
        val items =
            mutableListOf(
                Item("About", "orderFrontStandardAboutPanel:"),
                Item("Services", "", MemorySegment.ofAddress(4)),
                Item("Services", "", registered),
                Item("Hide", "hide:"),
                Item("Quit", "terminate:"),
            )

        override fun onMainThread(action: () -> Unit) {
            check(!onMain)
            onMain = true
            try {
                action()
            } finally {
                onMain = false
            }
        }

        override fun application(): MemorySegment = app.also { check(onMain) }

        override fun servicesMenu(application: MemorySegment): MemorySegment = registered.also { check(onMain && application == app) }

        override fun supermenu(menu: MemorySegment): MemorySegment = parent.also { check(onMain && menu == registered) }

        override fun indexOfSubmenu(
            menu: MemorySegment,
            submenu: MemorySegment,
        ): Long {
            check(onMain && menu == container)
            return if (missingIndex) -1 else items.indexOfFirst { it.submenu == submenu }.toLong()
        }

        override fun removeItem(
            menu: MemorySegment,
            index: Long,
        ) {
            check(onMain && menu == container)
            changes += "remove:$index"
            if (!ignoreRemove) {
                items.removeAt(index.toInt())
                if (!ignoreDetach) parent = MemorySegment.NULL
            }
        }
    }
}
