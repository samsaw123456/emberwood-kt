package emberwood

import java.awt.event.KeyEvent
import java.nio.file.Files
import javax.swing.SwingUtilities
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class JumpInputOrderTest {
    private val keys = listOf(KeyEvent.VK_SPACE, KeyEvent.VK_W, KeyEvent.VK_UP)

    @Test
    fun releaseThenPressPreservesTheNewAirJumpForEveryBindingPair() {
        for (first in keys) {
            for (second in keys) {
                withPanel { panel ->
                    key(panel, first, true)
                    step(panel)
                    assertEquals(1, panel.game.player.jumpsLeft)
                    key(panel, first, false)
                    key(panel, second, true)
                    step(panel)
                    assertEquals(0, panel.game.player.jumpsLeft, "Both presses must consume their own jump")
                    assertFullRise(panel, "${KeyEvent.getKeyText(first)} up then ${KeyEvent.getKeyText(second)} down")
                }
            }
        }
    }

    @Test
    fun pressThenReleaseStillMakesAShortJump() {
        for (binding in keys) {
            withPanel { panel ->
                val ground = panel.game.player.y
                key(panel, binding, true)
                key(panel, binding, false)
                step(panel)
                assertEquals(1, panel.game.player.jumpsLeft)
                assertTrue(panel.game.player.y < ground, "A short tap must still leave the ground")
                assertTrue(panel.game.player.vy in -300.0..-150.0, "The later release must shorten the jump")
                assertFalse(panel.game.player.jumpCutAvailable)
            }
        }
    }

    @Test
    fun pressReleasePressWithinOneStepKeepsTheFinalPressHeld() {
        for (first in keys) {
            for (last in keys) {
                withPanel { panel ->
                    key(panel, first, true)
                    key(panel, first, false)
                    key(panel, last, true)
                    step(panel)
                    assertEquals(1, panel.game.player.jumpsLeft, "Coalesced presses spend one simulation-step jump")
                    assertFullRise(panel, "The final press remains held")
                }
            }
        }
    }

    @Test
    fun releaseAfterLandingCannotCutTheNextImmediateGroundJump() {
        for (binding in keys) {
            withPanel { panel ->
                key(panel, binding, true)
                repeat(90) { step(panel) }
                assertTrue(panel.game.player.grounded, "Holding a jump must allow landing without another jump")
                key(panel, binding, false)
                key(panel, binding, true)
                step(panel)
                assertEquals(1, panel.game.player.jumpsLeft)
                assertFullRise(panel, "Release of the previous landed jump must not shorten the next jump")
            }
        }
    }

    @Test
    fun overlappingAlternateBindingsReleaseOnlyWhenEveryKeyIsUp() {
        for (first in keys) {
            for (second in keys.filter { it != first }) {
                withPanel { panel ->
                    key(panel, first, true)
                    step(panel)
                    key(panel, second, true)
                    key(panel, first, false)
                    step(panel)
                    assertEquals(1, panel.game.player.jumpsLeft, "An alternate held key must not spend an air jump")
                    assertFullRise(panel, "The alternate binding still holds the first jump")
                    key(panel, second, false)
                    step(panel)
                    assertTrue(panel.game.player.vy in -300.0..-150.0, "Releasing the final binding cuts the current jump")
                    assertFalse(panel.game.player.jumpCutAvailable)
                }
            }
        }
    }

    @Test
    fun nativeKeyRepeatsDoNotSpendTheAirJumpOrReapplyAnImpulse() {
        for (binding in keys) {
            withPanel { panel ->
                key(panel, binding, true)
                step(panel)
                val firstVelocity = panel.game.player.vy
                repeat(3) {
                    key(panel, binding, true)
                    step(panel)
                }
                assertEquals(1, panel.game.player.jumpsLeft)
                assertTrue(panel.game.player.vy > firstVelocity, "Held-key repeats must not restart the upward impulse")
                assertTrue(panel.game.player.jumpCutAvailable)
            }
        }
    }

    @Test
    fun focusLossAndPauseClearPendingJumpEdgesBeforeResume() {
        for (loseFocus in listOf(false, true)) {
            withPanel { panel ->
                key(panel, KeyEvent.VK_SPACE, true)
                key(panel, KeyEvent.VK_SPACE, false)
                key(panel, KeyEvent.VK_W, true)
                if (loseFocus) {
                    panel.loseFocus()
                } else {
                    key(panel, KeyEvent.VK_ESCAPE, true)
                    key(panel, KeyEvent.VK_ESCAPE, false)
                }
                assertEquals(GameState.PAUSED, panel.game.state)
                key(panel, KeyEvent.VK_W, false)
                key(panel, KeyEvent.VK_ESCAPE, true)
                key(panel, KeyEvent.VK_ESCAPE, false)
                step(panel)
                assertEquals(GameState.PLAYING, panel.game.state)
                assertTrue(panel.game.player.grounded, "Resume must not replay pending jump edges")
                assertEquals(2, panel.game.player.jumpsLeft)
                key(panel, KeyEvent.VK_SPACE, true)
                step(panel)
                assertFullRise(panel, "A fresh press after resume must still work")
            }
        }
    }

    private fun assertFullRise(
        panel: GamePanel,
        context: String,
    ) {
        assertFalse(panel.game.player.grounded, context)
        assertTrue(panel.game.player.vy < -400.0, "$context: velocity=${panel.game.player.vy}")
        assertTrue(panel.game.player.jumpCutAvailable, context)
    }

    private fun withPanel(body: (GamePanel) -> Unit) {
        val preferences = Files.createTempDirectory("emberwood-jump-order-")
        val audio = Audio { error("No hardware output is needed by the input-order regression") }
        try {
            SwingUtilities.invokeAndWait {
                GamePanel(Settings(preferences), audio).use { panel ->
                    // Keep real listeners, simulation and transition bookkeeping; the EDT block prevents timer interleaving.
                    key(panel, KeyEvent.VK_ENTER, true)
                    key(panel, KeyEvent.VK_ENTER, false)
                    step(panel)
                    assertTrue(panel.game.player.grounded)
                    body(panel)
                }
            }
        } finally {
            audio.close()
            preferences.toFile().deleteRecursively()
        }
    }

    private fun key(
        panel: GamePanel,
        binding: Int,
        down: Boolean,
    ) {
        val type = if (down) KeyEvent.KEY_PRESSED else KeyEvent.KEY_RELEASED
        val event = KeyEvent(panel, type, System.currentTimeMillis(), 0, binding, KeyEvent.CHAR_UNDEFINED, KeyEvent.KEY_LOCATION_STANDARD)
        panel.keyListeners.forEach { if (down) it.keyPressed(event) else it.keyReleased(event) }
    }

    private fun step(panel: GamePanel) {
        // Drive exactly one ordinary timer step without sleeping or replacing the production input mapper.
        GamePanel::class.java
            .getDeclaredField("accumulator")
            .apply { isAccessible = true }
            .setDouble(panel, 1.0 / 60)
        GamePanel::class.java
            .getDeclaredField("last")
            .apply { isAccessible = true }
            .setLong(panel, System.nanoTime())
        GamePanel::class.java
            .getDeclaredMethod("tick")
            .apply { isAccessible = true }
            .invoke(panel)
    }
}
