package emberwood

import java.awt.Rectangle
import java.awt.Robot
import java.awt.event.KeyEvent
import java.nio.file.Files
import java.nio.file.Path
import javax.imageio.ImageIO
import javax.swing.JFrame
import javax.swing.SwingUtilities

/** Original route driven through OS keys at the application's normal simulation rate. */
object CampaignAudit {
    @JvmStatic
    fun main(args: Array<String>) {
        val count = args.firstOrNull()?.toInt() ?: 3
        require(count in 1..20)
        val output = Path.of(System.getProperty("audit.output", "build/campaign-native"))
        Files.createDirectories(output)
        val preferences = Files.createTempDirectory("emberwood-campaign-")
        val robot = Robot()
        var frame: JFrame? = null
        var panel: GamePanel? = null
        val held = mutableSetOf<Int>()
        val results = mutableListOf<String>()

        fun edt(action: () -> Unit) = SwingUtilities.invokeAndWait(action)

        fun key(
            code: Int,
            down: Boolean,
        ) {
            if (down && held.add(code)) robot.keyPress(code)
            if (!down && held.remove(code)) robot.keyRelease(code)
        }

        fun release() = held.toList().forEach { key(it, false) }

        fun snap(label: String) {
            robot.waitForIdle()
            var bounds = Rectangle()
            edt {
                val view = checkNotNull(panel)
                val p = view.locationOnScreen
                bounds = Rectangle(p.x, p.y, view.width, view.height)
            }
            ImageIO.write(robot.createScreenCapture(bounds), "png", output.resolve("$label.png").toFile())
        }
        try {
            edt {
                val window = openWindow(Settings(preferences))
                frame = window.first
                panel = window.second
            }
            robot.delay(600)
            snap("title")
            key(KeyEvent.VK_ENTER, true)
            robot.delay(40)
            release()
            robot.delay(150)
            val game = checkNotNull(panel).game
            check(game.state == GameState.PLAYING) { "Initial Return did not start the game" }
            for (chapter in 0 until count) {
                check(game.stageIndex == chapter)
                val driver =
                    RouteDriver(game) { input ->
                        var age = 0.0
                        edt { age = game.level.age }
                        key(KeyEvent.VK_A, input.left)
                        key(KeyEvent.VK_D, input.right)
                        key(KeyEvent.VK_SPACE, input.jumpHeld)
                        val deadline = System.nanoTime() + 2_000_000_000L
                        var advanced = false
                        while (!advanced) {
                            robot.delay(1)
                            edt { advanced = game.level.age > age || game.state != GameState.PLAYING }
                            check(System.nanoTime() < deadline) { "Game stopped advancing during native input" }
                        }
                    }
                snap("chapter-${chapter + 1}-entry")
                for ((index, route) in game.level.definition.route
                    .withIndex()) {
                    check(
                        driver.follow(route),
                    ) { "Chapter ${chapter + 1} route $index $route failed at ${game.player.position}, ${game.state}" }
                    if (index % 8 == 0) snap("chapter-${chapter + 1}-route-$index")
                }
                if (game.boss != null) {
                    snap("chapter-${chapter + 1}-boss-before")
                    check(driver.fightBoss()) { "Guardian ${game.boss?.name} was not defeated" }
                    snap("chapter-${chapter + 1}-boss-defeated")
                    check(driver.walk(game.level.gate.x))
                }
                release()
                check(game.level.takenAcorns.size == 3 && game.level.secretFound)
                check(game.state == if (chapter == 19) GameState.WON else GameState.CHAPTER_COMPLETE)
                snap("chapter-${chapter + 1}-complete")
                results.add("Chapter ${chapter + 1}: native keys reached exit, 3 acorns, hidden firefly; retries=${game.deaths}")
                println(results.last())
                if (chapter + 1 < count) {
                    key(KeyEvent.VK_ENTER, true)
                    robot.delay(40)
                    release()
                    robot.delay(120)
                }
            }
            check(game.deaths == 0)
            Files.writeString(output.resolve("results.txt"), results.joinToString("\n") + "\n")
        } finally {
            release()
            if (panel != null) snap("final")
            edt { frame?.dispose() }
            preferences.toFile().deleteRecursively()
        }
    }
}
