package emberwood

import java.nio.file.Path
import javax.swing.JFrame
import javax.swing.SwingUtilities
import kotlin.math.min
import kotlin.math.roundToInt

/** Positions the real window for output capture; mute actions still arrive through physical keys or mouse. */
object AudioStateFixture {
    @JvmStatic
    fun main(args: Array<String>) {
        require(args.size == 2 && args[0] == "--data-dir")
        lateinit var frame: JFrame
        lateinit var panel: GamePanel
        SwingUtilities.invokeAndWait {
            val window = openWindow(Settings(Path.of(args[1])))
            frame = window.first
            panel = window.second
        }
        println("READY")
        try {
            for (line in System.`in`.bufferedReader().lineSequence()) {
                if (line == "quit") break
                var response = ""
                SwingUtilities.invokeAndWait {
                    when {
                        line.startsWith("state ") -> {
                            val state = GameState.valueOf(line.substringAfter(' '))
                            panel.loseFocus()
                            panel.game.startRun()
                            if (state == GameState.RESPAWNING) {
                                panel.game.retry()
                                panel.game.respawnLeft = 1000.0
                            } else if (state == GameState.PAUSED) {
                                panel.game.pause()
                            } else {
                                panel.game.state = state
                            }
                            panel.game.drainSounds()
                            panel.audio.stop()
                            panel.rebuildActions()
                            frame.toFront()
                            panel.requestFocusInWindow()
                            panel.repaint()
                        }
                        line == "cue" || line.startsWith("cue ") -> {
                            val cue = line.substringAfter(' ', "gem")
                            require(cue == "gem" || cue == "win")
                            panel.audio.play(cue)
                        }
                        line == "status" || line == "sound-target" -> Unit
                        else -> error("Unknown fixture command: $line")
                    }
                    response =
                        if (line == "sound-target") {
                            soundTarget(panel)
                        } else {
                            listOf(
                                "OK",
                                panel.game.state,
                                panel.audio.muted,
                                panel.settings.muted,
                                panel.isFocusOwner,
                                panel.audio.unavailable ?: "available",
                            ).joinToString("\t")
                        }
                }
                println(response)
            }
        } finally {
            SwingUtilities.invokeAndWait { frame.dispose() }
        }
    }

    private fun soundTarget(panel: GamePanel): String {
        panel.rebuildActions()
        val sound = panel.actions.single { it.id == "sound" }
        val origin = panel.locationOnScreen
        val scale = min(panel.width / 1152.0, panel.height / 648.0)
        val x = origin.x + (panel.width - 1152 * scale) / 2 + sound.bounds.centerX * scale
        val y = origin.y + (panel.height - 648 * scale) / 2 + sound.bounds.centerY * scale
        return listOf("SOUND", panel.actions.getOrNull(panel.focusIndex)?.id ?: "none", x.roundToInt(), y.roundToInt()).joinToString("\t")
    }
}
