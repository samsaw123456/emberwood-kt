package emberwood

import java.awt.Rectangle
import java.awt.Robot
import java.awt.event.KeyAdapter
import java.awt.event.KeyEvent
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
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
        val delivery = ConcurrentHashMap<Pair<Int, Boolean>, CountDownLatch>()
        val observedInput = Game::class.java.getDeclaredField("lastInput").apply { isAccessible = true }
        val results = mutableListOf<String>()
        val trace = mutableListOf("Chapter\tRoute\tAge\tX\tY\tVX\tVY\tGrounded\tJumps\tLeft\tRight\tJump\tDash\tState")

        fun edt(action: () -> Unit) = SwingUtilities.invokeAndWait(action)

        fun postKey(
            code: Int,
            down: Boolean,
        ): CountDownLatch? {
            val changed = if (down) held.add(code) else held.remove(code)
            if (!changed) return null
            val received = CountDownLatch(1)
            delivery[code to down] = received
            if (down) robot.keyPress(code) else robot.keyRelease(code)
            return received
        }

        fun key(
            code: Int,
            down: Boolean,
        ) {
            val received = postKey(code, down) ?: return
            check(received.await(2, TimeUnit.SECONDS)) { "Physical key $code/$down did not reach the focused window" }
        }

        fun release() = held.toList().forEach { key(it, false) }

        fun snap(label: String) {
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
                window.second.addKeyListener(
                    object : KeyAdapter() {
                        override fun keyPressed(event: KeyEvent) {
                            delivery.remove(event.keyCode to true)?.countDown()
                        }

                        override fun keyReleased(event: KeyEvent) {
                            delivery.remove(event.keyCode to false)?.countDown()
                        }
                    },
                )
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
                var routeIndex = -1
                val driver =
                    RouteDriver(game, nativeTiming = true) { input ->
                        // Post a human chord together; waiting after each key would
                        // turn a move-and-jump into a walk followed by a late jump.
                        val pending =
                            listOf(
                                KeyEvent.VK_A to input.left,
                                KeyEvent.VK_D to input.right,
                                KeyEvent.VK_SPACE to input.jumpHeld,
                                KeyEvent.VK_SHIFT to input.dashHeld,
                            ).mapNotNull { (code, down) -> postKey(code, down) }
                        pending.forEach { check(it.await(2, TimeUnit.SECONDS)) { "Physical chord did not reach the focused window" } }
                        var age = 0.0
                        edt { age = game.level.age }
                        val deadline = System.nanoTime() + 2_000_000_000L
                        var advanced = false
                        while (!advanced) {
                            robot.delay(1)
                            edt {
                                val applied = observedInput.get(game) as InputFrame
                                advanced = game.state != GameState.PLAYING ||
                                    (
                                        game.level.age > age &&
                                            applied.left == input.left &&
                                            applied.right == input.right &&
                                            applied.jumpHeld == input.jumpHeld &&
                                            applied.dashHeld == input.dashHeld
                                    )
                                if (advanced) {
                                    val p = game.player
                                    trace.add(
                                        listOf(
                                            chapter + 1,
                                            routeIndex,
                                            game.level.age,
                                            p.x,
                                            p.y,
                                            p.vx,
                                            p.vy,
                                            p.grounded,
                                            p.jumpsLeft,
                                            applied.left,
                                            applied.right,
                                            applied.jumpHeld,
                                            applied.dashHeld,
                                            game.state,
                                        ).joinToString("\t"),
                                    )
                                }
                            }
                            check(System.nanoTime() < deadline) { "Game stopped advancing during native input" }
                        }
                    }
                snap("chapter-${chapter + 1}-entry")
                var resumeAt = 0
                var completed = false
                for (attempt in 0..8) {
                    var reachedRouteEnd = true
                    for ((index, route) in game.level.definition.route
                        .withIndex()
                        .drop(resumeAt)) {
                        routeIndex = index
                        // Stop outside the opossum's whole patrol before jumping.
                        val approach = if (chapter == 0 && index == 4) route.copy(x = 1225.0) else route
                        if (!driver.follow(approach)) {
                            reachedRouteEnd = false
                            break
                        }
                        println("Chapter ${chapter + 1}, route $index: ${game.player.position}; age=${game.level.age}")
                    }
                    if (reachedRouteEnd && game.boss != null) {
                        routeIndex = -2
                        release()
                        snap("chapter-${chapter + 1}-boss-before-$attempt")
                        reachedRouteEnd = driver.fightBoss()
                        if (reachedRouteEnd) {
                            release()
                            snap("chapter-${chapter + 1}-boss-defeated")
                            reachedRouteEnd = driver.walk(game.level.gate.x)
                        }
                    }
                    release()
                    if (reachedRouteEnd) {
                        completed = true
                        break
                    }
                    val failure =
                        "Chapter ${chapter + 1}, attempt ${attempt + 1}, route $routeIndex: " +
                            "${game.player.position}, ${game.state}"
                    println("Retry: $failure")
                    results.add("Retry: $failure")
                    snap("chapter-${chapter + 1}-retry-${attempt + 1}")
                    check(attempt < 8) { "Native route retry limit reached: $failure" }
                    // Use the real retry command and campfire, never reset game
                    // fields or move the fox. Deaths remain in the final record.
                    if (game.state == GameState.PLAYING) {
                        key(KeyEvent.VK_R, true)
                        robot.delay(40)
                        release()
                    }
                    val deadline = System.nanoTime() + 5_000_000_000L
                    while (game.state == GameState.RESPAWNING && System.nanoTime() < deadline) robot.delay(10)
                    check(game.state == GameState.PLAYING) { "Campfire recovery did not complete: ${game.state}" }
                    val camp = game.level.camps[game.level.campIndex]
                    check(kotlin.math.abs(game.player.x - camp.x) < 2) { "Retry did not return to the active campfire" }
                    resumeAt =
                        game.level.definition.route
                            .indexOfFirst { it.x > camp.x + 20 }
                    if (resumeAt < 0) resumeAt = game.level.definition.route.size
                }
                check(completed)
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
        } finally {
            release()
            if (panel != null) snap("final")
            edt { frame?.dispose() }
            Files.writeString(output.resolve("input-route.tsv"), trace.joinToString("\n") + "\n")
            Files.writeString(output.resolve("results.txt"), results.joinToString("\n") + "\n")
            preferences.toFile().deleteRecursively()
        }
    }
}
