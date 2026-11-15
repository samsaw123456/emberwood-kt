package emberwood

import java.nio.file.Path
import javax.swing.JFrame
import javax.swing.SwingUtilities

/** Positions the real window for output capture; all mute actions still arrive through physical M keys. */
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
                        line == "cue" -> panel.audio.play("gem")
                        line == "status" -> Unit
                        else -> error("Unknown fixture command: $line")
                    }
                    response =
                        listOf(
                            "OK",
                            panel.game.state,
                            panel.audio.muted,
                            panel.settings.muted,
                            panel.isFocusOwner,
                            panel.audio.unavailable ?: "available",
                        ).joinToString("\t")
                }
                println(response)
            }
        } finally {
            SwingUtilities.invokeAndWait { frame.dispose() }
        }
    }
}
