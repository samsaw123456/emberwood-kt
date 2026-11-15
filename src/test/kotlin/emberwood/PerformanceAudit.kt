package emberwood

import com.sun.management.OperatingSystemMXBean
import java.awt.Robot
import java.awt.event.KeyEvent
import java.lang.management.ManagementFactory
import java.nio.file.Files
import java.nio.file.Path
import java.util.Locale
import javax.imageio.ImageIO
import javax.swing.JFrame
import javax.swing.SwingUtilities
import kotlin.math.abs
import kotlin.math.max

/** Real-window resource measurements. Scene fixtures are explicitly separate from physical-input play. */
object PerformanceAudit {
    @JvmStatic
    fun main(args: Array<String>) {
        require(args.isEmpty()) { "Configure with -Dperformance.output and -Dperformance.soakSeconds, not command arguments." }
        Audit(
            Path.of(System.getProperty("performance.output", "build/performance")),
            System.getProperty("performance.soakSeconds", "180").toDouble(),
        ).run()
    }

    private data class Snapshot(
        val wallNanos: Long,
        val cpuNanos: Long,
        val frames: Long,
        val paintNanos: Long,
        val elapsed: Double,
        val state: GameState,
        val heapBytes: Long,
        val shots: Int,
        val particles: Int,
    )

    private class Audit(
        private val output: Path,
        private val soakSeconds: Double,
    ) {
        private val robot = Robot().apply { autoDelay = 3 }
        private val operatingSystem = ManagementFactory.getOperatingSystemMXBean() as OperatingSystemMXBean
        private val memory = ManagementFactory.getMemoryMXBean()
        private val keys = mutableSetOf<Int>()
        private val rows = mutableListOf<String>()
        private val failures = mutableListOf<String>()
        private lateinit var window: JFrame
        private lateinit var panel: GamePanel

        fun run() {
            require(soakSeconds.isFinite() && soakSeconds >= 30 && soakSeconds <= 1800)
            Files.createDirectories(output)
            val preferences = Files.createTempDirectory("emberwood-performance-")
            try {
                edt {
                    val opened = openWindow(Settings(preferences))
                    window = opened.first
                    panel = opened.second
                }
                robot.delay(1000)
                screenshot("title-before")
                measure("title-idle", "idle", 6.0)
                screenshot("title-after")

                // Start, move, jump, release, retry, pause and resume use OS input.
                physicalCoreLoop()
                measure("pause-idle", "idle", 6.0)
                screenshot("pause-after")
                tap(KeyEvent.VK_ESCAPE)

                for (level in Levels.all.distinctBy { it.theme }) {
                    scene(level.index, level.camps.first())
                    measure("theme-${level.theme}", "scene fixture", 3.0, active = true)
                    screenshot("theme-${level.theme}")
                }
                for (monster in Levels.all.first().critters) {
                    scene(0, monster.home - Vec(monster.range + 40, 0.0))
                    measure("monster-${monster.kind}", "scene fixture", 3.0, active = true)
                    screenshot("monster-${monster.kind}")
                }
                for (chapter in listOf(2, 5, 8, 11, 14, 17)) {
                    scene(chapter, Vec(if (chapter == 2) 2660.0 else 3060.0, 536.0), boss = true)
                    val species = edt { panel.game.boss!!.species }
                    measure("boss-$species", "scene fixture", 4.0, active = true)
                    screenshot("boss-$species")
                }

                // Original first-level terrain; only gear is pre-unlocked for sustained projectile load.
                scene(0, Vec(140.0, 536.0), gear = true)
                measure("soak-warmup", "physical input after gear fixture", 6.0, active = true, input = ::soakInput)
                releaseKeys()
                val liveBefore = liveHeap()
                screenshot("soak-before")
                measure("active-soak", "physical input after gear fixture", soakSeconds, active = true, input = ::soakInput)
                releaseKeys()
                robot.delay(1200)
                val liveAfter = liveHeap()
                screenshot("soak-after")
                verify(liveAfter - liveBefore < 16L * 1024 * 1024, "Retained heap grew by more than 16 MiB during the soak")
                verify(edt { panel.game.state == GameState.PLAYING && panel.game.deaths == 0 }, "Soak unexpectedly died or left gameplay")
                val maximumHeap = Runtime.getRuntime().maxMemory()
                verify(maximumHeap <= 144L * 1024 * 1024, "Audit was not launched with the required 128 MiB heap limit")
                verify(Runtime.getRuntime().availableProcessors() <= 2, "Audit was not launched with ActiveProcessorCount=2")
                Files.writeString(
                    output.resolve("summary.txt"),
                    buildString {
                        appendLine("Emberwood Kotlin real-window performance audit")
                        appendLine("Java: ${System.getProperty("java.version")}")
                        appendLine("OS: ${System.getProperty("os.name")} ${System.getProperty("os.arch")}")
                        appendLine("Processors visible to JVM: ${Runtime.getRuntime().availableProcessors()}")
                        appendLine("Maximum Java heap bytes: $maximumHeap")
                        appendLine("Window content pixels: ${edt { "${panel.width} x ${panel.height}" }}")
                        appendLine("Audio device: ${panel.audio.unavailable ?: "opened; original cues enabled"}")
                        appendLine("Live heap before/after soak bytes: $liveBefore / $liveAfter")
                        appendLine("Soak seconds: $soakSeconds")
                        appendLine("Scene fixtures load original terrain and position the fox; boss fixtures grant acorns and armor.")
                        appendLine("Core play and the soak use Robot keys. Fixtures do not count as campaign/control coverage.")
                        appendLine("CPU is process CPU divided by wall time; 100% means one fully occupied core.")
                        appendLine("Limits: active scenes >=45 painted frames/s, mean paint <=16.67 ms, simulation >=90% of wall time.")
                        appendLine("Idle limits: <=2 painted frames/s, zero simulation progress; heap drift <=16 MiB after collection.")
                        appendLine("Results: ${if (failures.isEmpty()) "PASS" else "FAIL"}")
                        failures.forEach { appendLine(it) }
                    },
                )
            } finally {
                releaseKeys()
                if (::window.isInitialized) edt { window.dispose() }
                Files.writeString(
                    output.resolve("measurements.tsv"),
                    "Scene\tMethod\tWall seconds\tSimulation seconds\tProcess CPU percent\tPainted frames/s\t" +
                        "Mean paint ms\tPeak sampled heap bytes\tPeak shots\tPeak particles\tResult\n" +
                        rows.joinToString("\n") + "\n",
                )
                preferences.toFile().deleteRecursively()
            }
            check(failures.isEmpty()) { failures.joinToString("\n") }
            println("Performance audit passed: ${rows.size} measured windows, $soakSeconds-second input soak. See $output")
        }

        private fun physicalCoreLoop() {
            tap(KeyEvent.VK_ENTER)
            robot.delay(150)
            val start = edt { panel.game.player.x }
            desiredKeys(setOf(KeyEvent.VK_D))
            robot.delay(420)
            releaseKeys()
            screenshot("core-right")
            verify(edt { panel.game.player.x > start + 65 }, "Physical D input did not move right during core play")
            desiredKeys(setOf(KeyEvent.VK_SPACE))
            robot.delay(130)
            screenshot("core-jump")
            verify(edt { panel.game.player.y < 510 }, "Physical Space did not jump during core play")
            releaseKeys()
            robot.delay(650)
            desiredKeys(setOf(KeyEvent.VK_A))
            robot.delay(420)
            releaseKeys()
            robot.delay(150)
            screenshot("core-left-release")
            verify(
                edt { panel.game.player.x < start + 25 && abs(panel.game.player.vx) < 0.01 },
                "Physical A/release did not recover to rest",
            )
            tap(KeyEvent.VK_R)
            robot.delay(950)
            screenshot("core-retry")
            verify(edt { panel.game.deaths == 1 && panel.game.player.grounded }, "Physical R did not complete a retry")
            tap(KeyEvent.VK_ESCAPE)
            screenshot("pause-before")
            verify(edt { panel.game.state == GameState.PAUSED }, "Physical Escape did not pause")
        }

        private fun scene(
            chapter: Int,
            position: Vec,
            boss: Boolean = false,
            gear: Boolean = false,
        ) {
            releaseKeys()
            edt {
                panel.loseFocus()
                panel.game.startRun()
                panel.game.loadChapter(chapter)
                panel.game.player.reset(position)
                panel.game.cameraX = (position.x - 380).coerceIn(0.0, max(0.0, panel.game.level.width - 1152))
                if (boss || gear) {
                    panel.game.equipment.rewardsAt(19, 9)
                    panel.game.equipment.equip("thorn_fan", true)
                }
                if (boss) {
                    panel.game.level.takenAcorns
                        .addAll(panel.game.level.acorns.indices)
                }
                panel.requestFocusInWindow()
                panel.repaint()
            }
            robot.delay(350)
            verify(edt { window.isFocused && panel.isFocusOwner }, "Window lost focus before scene $chapter")
        }

        private fun soakInput(seconds: Double) {
            val phase = seconds % 2.4
            val desired = mutableSetOf<Int>()
            val (x, speed) = edt { panel.game.player.x to panel.game.player.vx }
            val distance = (if (phase < 1.2) 320.0 else 140.0) - x
            val stoppingDistance = max(6.0, abs(speed) * 0.06)
            if (distance > stoppingDistance) desired.add(KeyEvent.VK_D)
            if (distance < -stoppingDistance) desired.add(KeyEvent.VK_A)
            if (phase >= 0.45 && phase < 0.62) desired.add(KeyEvent.VK_SPACE)
            if (phase >= 1.7 && phase < 1.78) desired.add(KeyEvent.VK_J)
            desiredKeys(desired)
        }

        private fun measure(
            name: String,
            method: String,
            seconds: Double,
            active: Boolean = false,
            input: (Double) -> Unit = {},
        ) {
            val before = snapshot()
            var peakHeap = before.heapBytes
            var peakShots = before.shots
            var peakParticles = before.particles
            var pollAt = 0.0
            while (true) {
                val elapsed = (System.nanoTime() - before.wallNanos) / 1e9
                if (elapsed >= seconds) break
                input(elapsed)
                if (elapsed >= pollAt) {
                    val current = snapshot()
                    peakHeap = max(peakHeap, current.heapBytes)
                    peakShots = max(peakShots, current.shots)
                    peakParticles = max(peakParticles, current.particles)
                    pollAt += 0.25
                }
                robot.delay(20)
            }
            releaseKeys()
            val after = snapshot()
            val wall = (after.wallNanos - before.wallNanos) / 1e9
            val simulation = after.elapsed - before.elapsed
            val frames = after.frames - before.frames
            val fps = frames / wall
            val paint = if (frames > 0) (after.paintNanos - before.paintNanos) / 1e6 / frames else 0.0
            val cpu = (after.cpuNanos - before.cpuNanos) / 1e9 / wall * 100
            val previousFailures = failures.size
            if (active) {
                verify(after.state == GameState.PLAYING, "$name did not remain in gameplay")
                verify(fps >= 45, "$name rendered at ${decimal(fps)} frames/s, below 45")
                verify(paint <= 1000.0 / 60, "$name average paint took ${decimal(paint)} ms, above 16.67")
                verify(simulation / wall >= 0.9, "$name simulation lagged wall time: ${decimal(simulation / wall * 100)}%")
            } else {
                verify(simulation == 0.0, "$name advanced simulation while idle")
                verify(fps <= 2, "$name repainted ${decimal(fps)} frames/s while idle")
            }
            val result = if (previousFailures == failures.size) "PASS" else "FAIL"
            rows.add(
                listOf(
                    name,
                    method,
                    decimal(wall),
                    decimal(simulation),
                    decimal(cpu),
                    decimal(fps),
                    decimal(paint),
                    peakHeap,
                    peakShots,
                    peakParticles,
                    result,
                ).joinToString("\t"),
            )
            println("$name: $result; ${decimal(fps)} frames/s, ${decimal(paint)} ms paint, ${decimal(cpu)}% CPU, $peakHeap heap bytes")
        }

        private fun snapshot(): Snapshot =
            edt {
                Snapshot(
                    System.nanoTime(),
                    operatingSystem.processCpuTime,
                    panel.paintedFrames,
                    panel.paintNanos,
                    panel.game.elapsed,
                    panel.game.state,
                    memory.heapMemoryUsage.used,
                    panel.game.shots.size,
                    panel.game.particles.size,
                )
            }

        private fun liveHeap(): Long {
            System.gc()
            robot.delay(400)
            return memory.heapMemoryUsage.used
        }

        private fun screenshot(name: String) {
            edt { panel.repaint() }
            robot.waitForIdle()
            robot.delay(30)
            val rectangle =
                edt {
                    val location = panel.locationOnScreen
                    java.awt.Rectangle(location.x, location.y, panel.width, panel.height)
                }
            ImageIO.write(robot.createScreenCapture(rectangle), "png", output.resolve("$name.png").toFile())
        }

        private fun desiredKeys(desired: Set<Int>) {
            for (key in keys.toList()) {
                if (key !in desired) {
                    robot.keyRelease(key)
                    keys.remove(key)
                }
            }
            for (key in desired) if (keys.add(key)) robot.keyPress(key)
        }

        private fun releaseKeys() = desiredKeys(emptySet())

        private fun tap(key: Int) {
            desiredKeys(setOf(key))
            robot.delay(35)
            releaseKeys()
            robot.delay(70)
        }

        private fun verify(
            condition: Boolean,
            message: String,
        ) {
            if (!condition) {
                failures.add(message)
                System.err.println(message)
            }
        }

        private fun decimal(number: Double) = String.format(Locale.ROOT, "%.3f", number)

        private fun <T> edt(action: () -> T): T {
            var value: Any? = null
            var failure: Throwable? = null
            SwingUtilities.invokeAndWait {
                try {
                    value = action()
                } catch (error: Throwable) {
                    failure = error
                }
            }
            failure?.let { throw it }
            @Suppress("UNCHECKED_CAST")
            return value as T
        }
    }
}
