package emberwood

import java.awt.event.KeyEvent
import java.awt.image.BufferedImage
import java.lang.reflect.Proxy
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.atomic.AtomicBoolean
import javax.imageio.ImageIO
import javax.sound.sampled.SourceDataLine
import javax.swing.SwingUtilities
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AudioStatusTest {
    @Test
    fun unavailableOutputDoesNotBecomeSoundOnOrOffWhenThePreferenceChanges() {
        withPanel(Audio { error("No output device") }) { panel ->
            assertEquals("No output device", panel.audio.unavailable)
            for (state in GameState.entries) {
                panel.game.state = state
                val before = render(panel, "unavailable-$state-before")
                val preference = panel.settings.muted
                toggle(panel)
                val after = render(panel, "unavailable-$state-after")
                assertEquals(!preference, panel.settings.muted, "The saved preference still toggles in $state")
                assertTrue(pixels(before).contentEquals(pixels(after)), "$state must keep displaying unavailable output")
                if (state == GameState.TITLE || state == GameState.PAUSED) {
                    assertEquals("Sound unavailable", panel.actions.single { it.id == "sound" }.text)
                }
            }
        }
    }

    @Test
    fun availableOutputStillShowsEachMuteChangeInEveryState() {
        val open = AtomicBoolean(true)
        val device =
            Proxy.newProxyInstance(
                SourceDataLine::class.java.classLoader,
                arrayOf(SourceDataLine::class.java),
            ) { _, method, args ->
                when (method.name) {
                    "open", "start", "flush" -> null
                    "write" -> {
                        Thread.sleep(2)
                        args[2]
                    }
                    "close" -> {
                        open.set(false)
                        null
                    }
                    "isOpen", "isRunning" -> open.get()
                    else -> error("Unexpected audio operation: ${method.name}")
                }
            } as SourceDataLine
        withPanel(Audio { device }) { panel ->
            assertTrue(panel.audio.ready)
            for (state in GameState.entries) {
                panel.game.state = state
                val before = render(panel, "available-$state-before")
                val preference = panel.settings.muted
                toggle(panel)
                val after = render(panel, "available-$state-after")
                assertEquals(!preference, panel.settings.muted)
                assertTrue(!pixels(before).contentEquals(pixels(after)), "$state must visibly report the mute change")
                if (state == GameState.TITLE || state == GameState.PAUSED) {
                    val expected = if (panel.settings.muted) "Sound: off" else "Sound: on"
                    assertEquals(expected, panel.actions.single { it.id == "sound" }.text)
                }
            }
        }
    }

    private fun withPanel(
        audio: Audio,
        body: (GamePanel) -> Unit,
    ) {
        val preferences = Files.createTempDirectory("emberwood-sound-status-")
        try {
            val deadline = System.nanoTime() + 2_000_000_000L
            while (!audio.ready && audio.unavailable == null && System.nanoTime() < deadline) Thread.sleep(5)
            assertTrue(audio.ready || audio.unavailable != null)
            SwingUtilities.invokeAndWait {
                GamePanel(Settings(preferences), audio).use { panel ->
                    panel.setSize(1152, 648)
                    // The EDT stays in this block so simulation timers cannot alter compared frames.
                    body(panel)
                }
            }
        } finally {
            audio.close()
            preferences.toFile().deleteRecursively()
        }
    }

    private fun toggle(panel: GamePanel) {
        val pressed = KeyEvent(panel, KeyEvent.KEY_PRESSED, 1, 0, KeyEvent.VK_M, 'm')
        val released = KeyEvent(panel, KeyEvent.KEY_RELEASED, 2, 0, KeyEvent.VK_M, 'm')
        panel.keyListeners.forEach { it.keyPressed(pressed) }
        panel.keyListeners.forEach { it.keyReleased(released) }
    }

    private fun render(
        panel: GamePanel,
        name: String,
    ): BufferedImage {
        val image = BufferedImage(1152, 648, BufferedImage.TYPE_INT_RGB)
        val graphics = image.createGraphics()
        try {
            panel.paint(graphics)
        } finally {
            graphics.dispose()
        }
        val output = Path.of("build", "audio-status-render")
        Files.createDirectories(output)
        ImageIO.write(image, "png", output.resolve("$name.png").toFile())
        return image
    }

    private fun pixels(image: BufferedImage) = image.getRGB(0, 0, image.width, image.height, null, 0, image.width)
}
