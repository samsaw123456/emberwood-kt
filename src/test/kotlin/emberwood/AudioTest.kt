package emberwood

import java.lang.reflect.Proxy
import java.util.concurrent.CountDownLatch
import java.util.concurrent.FutureTask
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import javax.sound.sampled.SourceDataLine
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AudioTest {
    @Test
    fun muteStillReturnsAndClosesAudioWhenTheOutputResetFails() {
        val writing = CountDownLatch(1)
        val closed = CountDownLatch(1)
        val device =
            Proxy.newProxyInstance(
                SourceDataLine::class.java.classLoader,
                arrayOf(SourceDataLine::class.java),
            ) { _, method, args ->
                when (method.name) {
                    "open", "start" -> null
                    "write" -> {
                        writing.countDown()
                        Thread.sleep(1)
                        args[2]
                    }
                    "flush" -> error("Output reset failed")
                    "close" -> {
                        closed.countDown()
                        null
                    }
                    "isOpen", "isRunning" -> closed.count != 0L
                    else -> error("Unexpected audio operation: ${method.name}")
                }
            } as SourceDataLine
        val audio = Audio { device }
        try {
            assertTrue(writing.await(2, TimeUnit.SECONDS))
            val mute = FutureTask { audio.muted = true }
            Thread(mute, "audio-mute-regression").apply { isDaemon = true }.start()
            mute.get(2, TimeUnit.SECONDS)
            assertTrue(audio.muted)
            assertTrue(closed.await(2, TimeUnit.SECONDS))
            assertEquals("Output reset failed", audio.unavailable)
            assertFalse(audio.ready)
        } finally {
            closed.countDown()
            audio.close()
        }
    }

    @Test
    fun blockedResetDoesNotHoldMuteOrQuitAndCannotResumePlaybackAfterQuit() {
        val writing = CountDownLatch(1)
        val resetting = CountDownLatch(1)
        val allowReset = CountDownLatch(1)
        val closed = CountDownLatch(1)
        val fullyReleased = CountDownLatch(1)
        val closes = AtomicInteger()
        val writes = AtomicInteger()
        val device =
            Proxy.newProxyInstance(
                SourceDataLine::class.java.classLoader,
                arrayOf(SourceDataLine::class.java),
            ) { _, method, args ->
                when (method.name) {
                    "open", "start" -> null
                    "write" -> {
                        writes.incrementAndGet()
                        writing.countDown()
                        Thread.sleep(1)
                        args[2]
                    }
                    "flush" -> {
                        resetting.countDown()
                        check(allowReset.await(5, TimeUnit.SECONDS))
                        null
                    }
                    "close" -> {
                        closed.countDown()
                        if (closes.incrementAndGet() == 2) fullyReleased.countDown()
                        null
                    }
                    "isOpen", "isRunning" -> closed.count != 0L
                    else -> error("Unexpected audio operation: ${method.name}")
                }
            } as SourceDataLine
        val audio = Audio { device }
        try {
            assertTrue(writing.await(2, TimeUnit.SECONDS))
            val mute = FutureTask { audio.muted = true }
            Thread(mute, "audio-blocked-reset-mute").apply { isDaemon = true }.start()
            mute.get(2, TimeUnit.SECONDS)
            assertTrue(resetting.await(2, TimeUnit.SECONDS))
            val beforeClose = writes.get()
            val closing = FutureTask { audio.close() }
            Thread(closing, "audio-blocked-reset-close").apply { isDaemon = true }.start()
            closing.get(2, TimeUnit.SECONDS)
            assertTrue(closed.await(1, TimeUnit.SECONDS))
            assertEquals(1L, allowReset.count, "The native reset is still blocked when Quit returns")
            allowReset.countDown()
            assertTrue(fullyReleased.await(2, TimeUnit.SECONDS), "The audio worker must finish after reset returns")
            assertEquals(beforeClose, writes.get(), "A late reset must not resume output after Quit")
            assertFalse(audio.ready)
        } finally {
            allowReset.countDown()
            audio.close()
        }
    }

    @Test
    fun aCueRequestedAfterStopSurvivesConcurrentDeferredResets() {
        val firstWrite = CountDownLatch(1)
        val allowFirstWrite = CountDownLatch(1)
        val resetting = CountDownLatch(1)
        val allowReset = CountDownLatch(1)
        val nextWrite = CountDownLatch(1)
        val closed = CountDownLatch(1)
        val resets = AtomicInteger()
        val writes = AtomicInteger()
        val prematureWrites = AtomicInteger()
        var nextBlock = byteArrayOf()
        val device =
            Proxy.newProxyInstance(
                SourceDataLine::class.java.classLoader,
                arrayOf(SourceDataLine::class.java),
            ) { _, method, args ->
                when (method.name) {
                    "open", "start" -> null
                    "write" -> {
                        if (writes.incrementAndGet() == 1) {
                            firstWrite.countDown()
                            check(allowFirstWrite.await(5, TimeUnit.SECONDS))
                        } else if (resets.get() < 2) {
                            prematureWrites.incrementAndGet()
                        } else {
                            val bytes = args[0] as ByteArray
                            val offset = args[1] as Int
                            nextBlock = bytes.copyOfRange(offset, offset + (args[2] as Int))
                            nextWrite.countDown()
                            check(closed.await(5, TimeUnit.SECONDS))
                        }
                        args[2]
                    }
                    "flush" -> {
                        if (resets.incrementAndGet() == 1) {
                            resetting.countDown()
                            check(allowReset.await(5, TimeUnit.SECONDS))
                        }
                        null
                    }
                    "close" -> {
                        closed.countDown()
                        null
                    }
                    "isOpen", "isRunning" -> closed.count != 0L
                    else -> error("Unexpected audio operation: ${method.name}")
                }
            } as SourceDataLine
        val audio = Audio { device }
        try {
            assertTrue(firstWrite.await(2, TimeUnit.SECONDS))
            audio.stop()
            allowFirstWrite.countDown()
            assertTrue(resetting.await(2, TimeUnit.SECONDS))
            audio.stop()
            audio.play("gem")
            allowReset.countDown()
            assertTrue(nextWrite.await(2, TimeUnit.SECONDS))
            assertEquals(2, resets.get())
            assertEquals(0, prematureWrites.get(), "A new cue must not be consumed ahead of the pending reset")
            assertEquals(0.toByte(), nextBlock[0])
            assertEquals(0.toByte(), nextBlock[1], "The cue must retain its initial zero-amplitude sample")
            assertTrue(nextBlock.any { it != 0.toByte() }, "The cue added after Stop must reach the output")
        } finally {
            allowFirstWrite.countDown()
            allowReset.countDown()
            closed.countDown()
            audio.close()
        }
    }

    @Test
    fun aMissingNativeOutputLibraryResolvesAsUnavailable() {
        val audio = Audio { throw UnsatisfiedLinkError("Output library unavailable") }
        try {
            val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2)
            while (audio.unavailable == null && System.nanoTime() < deadline) Thread.sleep(5)
            assertEquals("Output library unavailable", audio.unavailable)
            assertFalse(audio.ready)
        } finally {
            audio.close()
        }
    }

    @Test
    fun closingAnOpenDeviceDoesNotBlockOnItsNativeShutdown() {
        val writing = CountDownLatch(1)
        val closingDevice = CountDownLatch(1)
        val allowClose = CountDownLatch(1)
        val stopWrite = CountDownLatch(1)
        val closed = CountDownLatch(1)
        val device =
            Proxy.newProxyInstance(
                SourceDataLine::class.java.classLoader,
                arrayOf(SourceDataLine::class.java),
            ) { _, method, args ->
                when (method.name) {
                    "open", "start" -> null
                    "write" -> {
                        writing.countDown()
                        check(stopWrite.await(5, TimeUnit.SECONDS))
                        args[2]
                    }
                    "close" -> {
                        closingDevice.countDown()
                        check(allowClose.await(5, TimeUnit.SECONDS))
                        closed.countDown()
                        stopWrite.countDown()
                        null
                    }
                    "isOpen", "isRunning" -> closed.count != 0L
                    else -> error("Unexpected audio operation: ${method.name}")
                }
            } as SourceDataLine
        val audio = Audio { device }
        try {
            assertTrue(writing.await(2, TimeUnit.SECONDS))
            assertTrue(audio.ready)
            val closing = FutureTask { audio.close() }
            Thread(closing, "audio-close-regression").apply { isDaemon = true }.start()
            closing.get(2, TimeUnit.SECONDS)
            assertTrue(closingDevice.await(1, TimeUnit.SECONDS))
            assertFalse(audio.ready)
            assertEquals(1L, closed.count, "The provider is still blocked, but Quit must return")
            allowClose.countDown()
            assertTrue(closed.await(2, TimeUnit.SECONDS))
        } finally {
            allowClose.countDown()
            stopWrite.countDown()
            audio.close()
        }
    }

    @Test
    fun closingDuringBlockedDeviceInitializationReturnsAndReleasesTheDevice() {
        val opening = CountDownLatch(1)
        val allowOpen = CountDownLatch(1)
        val opened = CountDownLatch(1)
        val closed = CountDownLatch(1)
        val starts = AtomicInteger()
        val device =
            Proxy.newProxyInstance(
                SourceDataLine::class.java.classLoader,
                arrayOf(SourceDataLine::class.java),
            ) { _, method, _ ->
                when (method.name) {
                    "open" -> {
                        opening.countDown()
                        check(allowOpen.await(5, TimeUnit.SECONDS))
                        opened.countDown()
                        null
                    }
                    "start" -> {
                        starts.incrementAndGet()
                        null
                    }
                    "close" -> {
                        // Model a provider whose close takes the lock held by open.
                        check(opened.await(5, TimeUnit.SECONDS))
                        closed.countDown()
                        null
                    }
                    "isOpen" -> opened.count == 0L && closed.count != 0L
                    "isRunning" -> starts.get() > 0 && closed.count != 0L
                    else -> error("Unexpected audio operation: ${method.name}")
                }
            } as SourceDataLine
        val audio = Audio { device }
        try {
            assertTrue(opening.await(2, TimeUnit.SECONDS))
            assertFalse(audio.ready, "An initializing line is not ready for playback")
            val closing = FutureTask { audio.close() }
            Thread(closing, "audio-close-regression").apply { isDaemon = true }.start()
            closing.get(2, TimeUnit.SECONDS)
            assertEquals(1L, closed.count, "Quit must not enter the provider's blocked close")
            allowOpen.countDown()
            assertTrue(closed.await(2, TimeUnit.SECONDS), "The audio thread must release its late-opening device")
            assertEquals(0, starts.get(), "A device initialized after Quit must not start playback")
            assertFalse(audio.ready)
        } finally {
            allowOpen.countDown()
            audio.close()
        }
    }
}
