package emberwood

import java.awt.Graphics
import java.awt.RenderingHints
import java.awt.Robot
import java.awt.event.InputEvent
import java.awt.event.KeyAdapter
import java.awt.event.KeyEvent
import java.awt.event.MouseAdapter
import java.awt.event.MouseEvent
import java.awt.image.BufferedImage
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.ConcurrentHashMap
import javax.imageio.ImageIO
import javax.swing.JComponent
import javax.swing.JFrame
import javax.swing.SwingUtilities
import kotlin.math.abs

/** Native input and screen captures supplement, rather than replace, inspected presentation. */
fun main() {
    NativeAudit(Path.of(System.getProperty("audit.output", "build/audit"))).run()
}

private class NativeAudit(
    private val output: Path,
) {
    private lateinit var frame: JFrame
    private lateinit var panel: GamePanel
    private lateinit var keyboard: PhysicalKeys
    private val robot = if (NativeAuditTools.hasExternalController) null else Robot().apply { autoDelay = 8 }
    private lateinit var pointer: PhysicalPointer
    private val mouseDeliveries = ConcurrentHashMap<Pair<Int, Boolean>, Delivery>()
    private val rows = mutableListOf<String>()
    private val evidence = mutableListOf<String>()
    private val pendingImages = mutableListOf<Pair<String, BufferedImage>>()
    private val presentationTimings = mutableListOf<String>()
    private val presentationStages = mutableListOf<String>()
    private var presentationNonce = 65535

    private data class Delivery(
        val count: Int,
        val nanos: Long,
    )

    private val deliveries = ConcurrentHashMap<Triple<Int, Int, Boolean>, Delivery>()
    private val keyReceipts = mutableListOf<String>()
    private var wheelEvents = 0
    private var lastWheelRotation = 0
    private val inputTimings = mutableListOf<String>()

    @Volatile private var currentCase = "startup"
    private val selectedCases = System.getProperty("audit.filter")?.let(::Regex)
    private val macOS = System.getProperty("os.name").startsWith("Mac")
    private val observedDesktopState = GamePanel::class.java.getDeclaredField("previousState").apply { isAccessible = true }
    private val nativeKeys = mutableSetOf<String>()
    private var sequence = 0
    private var failures = 0
    private val menus = listOf(GameState.TITLE, GameState.PAUSED, GameState.CHAPTER_COMPLETE, GameState.WON)
    private val directions = listOf(KeyEvent.VK_A to -1, KeyEvent.VK_LEFT to -1, KeyEvent.VK_D to 1, KeyEvent.VK_RIGHT to 1)
    private val jumpKeys = listOf(KeyEvent.VK_SPACE, KeyEvent.VK_W, KeyEvent.VK_UP)
    private val activationKeys = listOf("Return", "Space", "Keypad Enter")

    fun run() {
        var failure: Throwable? = null
        try {
            execute()
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            try {
                writeCompletion(failure)
            } catch (recordError: Throwable) {
                val previous = failure
                if (previous == null) throw recordError else previous.addSuppressed(recordError)
            }
        }
    }

    private fun writeCompletion(error: Throwable?) {
        Files.createDirectories(output)
        val failed = rows.filter { it.split('\t').getOrNull(3)?.startsWith("FAIL") == true }
        val result = if (error == null && failures == 0) "PASS" else "FAIL"
        Files.writeString(
            output.resolve("completion.json"),
            "{\"result\":\"$result\",\"cases\":${rows.size},\"expected_cases\":280," +
                "\"filtered\":${selectedCases != null},\"failure_count\":$failures," +
                "\"failed_cases\":[${failed.joinToString(",") { NativeAuditTools.quote(it) }}]," +
                "\"exception\":${error?.let { NativeAuditTools.quote(it.toString()) } ?: "null"}}\n",
        )
    }

    private fun delay(milliseconds: Int) = Thread.sleep(milliseconds.toLong())

    private fun execute() {
        Files.createDirectories(output)
        val preferences = Files.createTempDirectory("emberwood-audit-")
        try {
            keyboard = PhysicalKeys(output.resolve("physical-os-state.jsonl"))
            inputTimings.add("startup\tserver\tOS\tready\t${keyboard.startupNanos / 1e6}")
            edt {
                val pair = openWindow(Settings(preferences))
                frame = pair.first
                panel = pair.second
                frame.glassPane =
                    object : JComponent() {
                        override fun contains(
                            x: Int,
                            y: Int,
                        ) = false

                        override fun paintComponent(graphics: Graphics) {
                            PresentationMarker.paint(graphics, presentationNonce)
                        }
                    }
                frame.glassPane.isVisible = true
                panel.addKeyListener(
                    object : KeyAdapter() {
                        override fun keyPressed(event: KeyEvent) = delivered(event, true)

                        override fun keyReleased(event: KeyEvent) = delivered(event, false)
                    },
                )
                panel.addMouseListener(
                    object : MouseAdapter() {
                        override fun mousePressed(event: MouseEvent) = deliveredMouse(event, true)

                        override fun mouseReleased(event: MouseEvent) = deliveredMouse(event, false)
                    },
                )
                panel.addMouseWheelListener { event ->
                    wheelEvents++
                    lastWheelRotation = event.wheelRotation
                }
            }
            delay(700)
            NativeInputGate.awaitReady(panel.audio, output)
            pointer = PhysicalPointer(robot)
            // Refuse an unavailable capture facility before attempting hundreds of controls.
            snap("presentation-startup")
            directionCases()
            gentleCameraDirections()
            jumpCases()
            dashCases()
            weaponCases()
            combinations()
            menuNavigation()
            menuActivation()
            gearAndSettings()
            gentleMotionPresentation()
            pauseAndRetry()
            disabledCases()
            mouseCases()
            focusCases()
            mouseFocusCase()
            resizeAndClose(preferences)
            println(
                "Native audit: ${rows.size} cases, $failures failures. " +
                    "Inspect every referenced screenshot; audio output is audited separately.",
            )
        } finally {
            try {
                releaseAll()
            } catch (failure: Throwable) {
                failures++
                failure.printStackTrace()
            }
            if (::pointer.isInitialized) {
                try {
                    pointer.close()
                } catch (failure: Throwable) {
                    failures++
                    failure.printStackTrace()
                }
            }
            if (::keyboard.isInitialized) {
                try {
                    keyboard.close()
                } catch (failure: Throwable) {
                    failures++
                    failure.printStackTrace()
                }
            }
            if (::frame.isInitialized) edt { frame.dispose() }
            try {
                NativeAuditTools.closeCapture()
            } catch (failure: Throwable) {
                failures++
                failure.printStackTrace()
            }
            flushImages()
            Files.writeString(
                output.resolve("controls.tsv"),
                "Binding\tState\tExpected observable effect\tAutomatic result\tEvidence (visual review required)\n" +
                    rows.joinToString("\n") +
                    "\n",
            )
            preferences.toFile().deleteRecursively()
            Files.writeString(
                output.resolve("input-latency.tsv"),
                "Case\tKey code\tLocation\tAction\tDelivery milliseconds\n" + inputTimings.joinToString("\n") + "\n",
            )
            Files.writeString(
                output.resolve("awt-key-receipts.jsonl"),
                edt { keyReceipts.joinToString("\n", postfix = "\n") },
            )
            Files.writeString(
                output.resolve("presentation-stages.jsonl"),
                presentationStages.joinToString("\n", postfix = "\n"),
            )
            Files.writeString(
                output.resolve("presentation-latency.tsv"),
                "Case\tFrame\tPresentation milliseconds\n" + presentationTimings.joinToString("\n") + "\n",
            )
        }
        check(failures == 0) { "$failures native control cases failed; see ${output.resolve("controls.tsv")}" }
    }

    private fun case(
        binding: String,
        state: GameState,
        expected: String,
        gear: Boolean = false,
        body: () -> Unit,
    ) {
        if (selectedCases != null && !selectedCases.containsMatchIn("$state/$binding")) return
        currentCase = "$state/$binding"
        evidence.clear()
        var result = "PASS automatic; visual review pending"
        try {
            fixture(state, gear)
            snap("$state-$binding-before")
            body()
            snap("$state-$binding-after")
        } catch (failure: Throwable) {
            failures++
            result = "FAIL: ${failure.message ?: failure.javaClass.simpleName}".replace('\t', ' ').replace('\n', ' ')
            System.err.println("$binding / $state: $result")
            failure.printStackTrace()
            if (::panel.isInitialized) runCatching { snap("$state-$binding-failure") }
        } finally {
            try {
                releaseAll()
            } catch (failure: Throwable) {
                failures++
                failure.printStackTrace()
                result = "FAIL recovery: ${failure.message}".replace('\t', ' ').replace('\n', ' ')
            }
            flushImages()
            rows.add("$binding\t$state\t$expected\t$result\t${evidence.joinToString(", ")}")
        }
    }

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

    private fun fixture(
        state: GameState,
        gear: Boolean,
    ) {
        edt {
            panel.loseFocus()
            panel.game.startRun()
            panel.game.reducedMotion = false
            panel.settings.gentle = false
            if (gear) {
                panel.game.equipment.rewardsAt(19, 9)
                panel.game.equipment.equip("bow", true)
                panel.game.equipment.equip("armor", true)
            }
            panel.game.player.reset(Vec(300.0, 536.0))
            panel.game.invincibleLeft = 0.0
        }
        // Desktop transitions run on its timer: let it observe PLAYING before preparing another menu.
        await("Fixture gameplay transition") { edt { panel.game.elapsed > 0 } }
        edt {
            when (state) {
                GameState.PAUSED -> panel.game.pause()
                GameState.RESPAWNING -> {
                    panel.game.retry()
                    panel.game.respawnLeft = 1000.0
                }
                else -> panel.game.state = state
            }
            panel.focusIndex = 0
            panel.rebuildActions()
            frame.toFront()
            panel.requestFocusInWindow()
            panel.repaint()
        }
        // Read-only fixture instrumentation: the desktop must finish transition bookkeeping before
        // the first physical key, otherwise its focus reset can undo a valid navigation step.
        await("Desktop observes staged $state transition") { edt { observedDesktopState.get(panel) == state } }
        await("Native window/panel keyboard focus") { edt { frame.isFocused && panel.isFocusOwner } }
    }

    private fun snap(
        label: String,
        observe: () -> Unit = {},
    ): BufferedImage {
        // waitForIdle repeatedly waits for this continuously animated window and extends held input.
        val started = System.nanoTime()
        val nonce = sequence

        fun stage(
            name: String,
            began: Long,
            extra: String = "",
        ) {
            presentationStages.add(
                "{\"case\":${NativeAuditTools.quote(currentCase)},\"frame\":${NativeAuditTools.quote(label)}," +
                    "\"nonce\":$nonce,\"stage\":${NativeAuditTools.quote(name)},\"startedNanos\":$began," +
                    "\"milliseconds\":${(System.nanoTime() - began) / 1e6}$extra}",
            )
        }
        edt {
            observe()
            presentationNonce = nonce
            frame.rootPane.paintImmediately(0, 0, frame.rootPane.width, frame.rootPane.height)
        }
        stage("edt-paint", started)
        val syncStarted = System.nanoTime()
        java.awt.Toolkit
            .getDefaultToolkit()
            .sync()
        stage("toolkit-sync", syncStarted)
        val boundsStarted = System.nanoTime()
        val bounds =
            edt {
                val p = panel.locationOnScreen
                java.awt.Rectangle(p.x, p.y, panel.width, panel.height)
            }
        stage("edt-bounds", boundsStarted)

        // Cocoa may return the previous compositor frame after paintImmediately. A marker in the
        // same window proves presentation; it never intercepts input or changes game state.
        var attempt = 0

        fun capture(): BufferedImage {
            val captureStarted = System.nanoTime()
            val image =
                if (NativeAuditTools.hasExternalController) {
                    NativeAuditTools.capture(bounds, output.resolve("external-capture.png"))
                } else {
                    checkNotNull(robot).createScreenCapture(bounds)
                }
            stage(
                "capture-read",
                captureStarted,
                ",\"attempt\":${++attempt},\"observedNonce\":${PresentationMarker.readNonce(image)}," +
                    "\"matched\":${PresentationMarker.matches(image, nonce)}",
            )
            return image
        }
        var image = capture()
        await("Desktop presentation for $label") {
            if (PresentationMarker.matches(image, nonce)) {
                true
            } else {
                image = capture()
                false
            }
        }
        val name = "%04d-%s.png".format(sequence++, label.replace(Regex("[^A-Za-z0-9-]"), "-").take(110))
        presentationTimings.add("$currentCase\t$name\t${(System.nanoTime() - started) / 1e6}")
        pendingImages.add(name to image)
        evidence.add(name)
        return logicalView(image)
    }

    private fun logicalView(image: BufferedImage): BufferedImage {
        if (image.width == 1152 && image.height == 648) return image
        // Only analysis is normalized. Evidence preserves the actual desktop size and letterbox.
        val scale = minOf(image.width / 1152.0, image.height / 648.0)
        val width = (1152 * scale).toInt()
        val height = (648 * scale).toInt()
        val x = (image.width - width) / 2
        val y = (image.height - height) / 2
        val normalized = BufferedImage(1152, 648, BufferedImage.TYPE_INT_RGB)
        val graphics = normalized.createGraphics()
        try {
            graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_NEAREST_NEIGHBOR)
            graphics.drawImage(image, 0, 0, 1152, 648, x, y, x + width, y + height, null)
        } finally {
            graphics.dispose()
        }
        return normalized
    }

    private fun flushImages() {
        for ((name, image) in pendingImages) check(ImageIO.write(image, "png", output.resolve(name).toFile()))
        pendingImages.clear()
    }

    private fun delivered(
        event: KeyEvent,
        down: Boolean,
    ) {
        val binding = Triple(event.keyCode, event.keyLocation, down)
        val received = System.nanoTime()
        keyReceipts.add(
            "{\"case\":${NativeAuditTools.quote(currentCase)},\"down\":$down," +
                "\"keyCode\":${event.keyCode},\"keyLocation\":${event.keyLocation}," +
                "\"modifiersEx\":${event.modifiersEx},\"eventMillis\":${event.`when`}," +
                "\"receivedNanos\":$received}",
        )
        deliveries[binding] = Delivery((deliveries[binding]?.count ?: 0) + 1, received)
    }

    private fun await(
        description: String,
        condition: () -> Boolean,
    ) {
        val deadline = System.nanoTime() + 3_000_000_000L
        while (!condition()) {
            check(System.nanoTime() < deadline) { "$description did not complete within three seconds" }
            delay(5)
        }
    }

    private fun received(
        binding: Triple<Int, Int, Boolean>,
        count: Int,
        started: Long,
    ) {
        await("Physical key event $binding") { (deliveries[binding]?.count ?: 0) >= count }
        val milliseconds = ((deliveries[binding]?.nanos ?: started) - started) / 1e6
        inputTimings.add("$currentCase\t${binding.first}\t${binding.second}\t${if (binding.third) "down" else "up"}\t$milliseconds")
    }

    private fun down(key: Int) = physical(PhysicalKeys.name(key) to true)

    private fun up(key: Int) = physical(PhysicalKeys.name(key) to false)

    private fun tap(key: Int) {
        down(key)
        delay(25)
        up(key)
        delay(45)
    }

    private fun physical(vararg events: Pair<String, Boolean>) {
        val expected = mutableMapOf<Triple<Int, Int, Boolean>, Int>()
        val shifted = nativeKeys.filter { it.endsWith("shift") }.toMutableSet()
        val aggregateOnly = mutableListOf<Pair<String, Boolean>>()
        for ((key, down) in events) {
            if (macOS && key.endsWith("shift")) {
                val wasShifted = shifted.isNotEmpty()
                if (down) shifted.add(key) else shifted.remove(key)
                if (wasShifted == shifted.isNotEmpty()) {
                    // OpenJDK AWTEvent.m reports modifiers only when aggregate flags change.
                    // physical_key.py independently verifies these OS key states.
                    aggregateOnly.add(key to down)
                    continue
                }
            }
            val (code, where) = PhysicalKeys.binding(key)
            val binding = Triple(code, where, down)
            expected[binding] = (expected[binding] ?: deliveries[binding]?.count ?: 0) + 1
        }
        val started = System.nanoTime()
        // A failed acknowledgement may still follow a delivered native press. Remember attempted
        // downs before running the helper so case recovery releases them instead of contaminating
        // later cases with an OS modifier that the test forgot to release.
        for ((key, down) in events) if (down) nativeKeys.add(key)
        keyboard.send(*events)
        for ((key, down) in aggregateOnly) {
            inputTimings.add("$currentCase\t$key\tOS\t$down (AWT aggregate unchanged)\t${(System.nanoTime() - started) / 1e6}")
        }
        for ((key, down) in events) if (down) nativeKeys.add(key) else nativeKeys.remove(key)
        if (edt { frame.isFocused }) for ((binding, count) in expected) received(binding, count, started)
    }

    private fun releaseAll() {
        var failure: Throwable? = null
        try {
            if (nativeKeys.isNotEmpty()) physical(*nativeKeys.map { it to false }.toTypedArray())
        } catch (error: Throwable) {
            failure = error
        }
        try {
            if (::pointer.isInitialized) pointer.releaseAll()
        } catch (error: Throwable) {
            val previous = failure
            if (previous == null) failure = error else previous.addSuppressed(error)
        }
        failure?.let { throw it }
    }

    private fun activate(
        key: String,
        hold: Boolean = false,
    ) {
        when (key) {
            "Return" -> down(KeyEvent.VK_ENTER)
            "Space" -> down(KeyEvent.VK_SPACE)
            else -> physical("keypad-enter" to true)
        }
        delay(if (hold) 850 else 25)
        if (hold) snap("activation-held")
        when (key) {
            "Return" -> up(KeyEvent.VK_ENTER)
            "Space" -> up(KeyEvent.VK_SPACE)
            else -> physical("keypad-enter" to false)
        }
        delay(45)
    }

    private fun deliveredMouse(
        event: MouseEvent,
        down: Boolean,
    ) {
        val binding = event.button to down
        mouseDeliveries.compute(binding) { _, previous -> Delivery((previous?.count ?: 0) + 1, System.nanoTime()) }
    }

    private fun mouseButton(
        mask: Int,
        down: Boolean,
    ) {
        val button =
            when (mask) {
                InputEvent.BUTTON1_DOWN_MASK -> MouseEvent.BUTTON1
                InputEvent.BUTTON2_DOWN_MASK -> MouseEvent.BUTTON2
                InputEvent.BUTTON3_DOWN_MASK -> MouseEvent.BUTTON3
                else -> error("Unsupported mouse mask $mask")
            }
        val binding = button to down
        val before = mouseDeliveries[binding]?.count ?: 0
        val expectPanel = edt { frame.isFocused && panel.isFocusOwner }
        val began = System.nanoTime()
        pointer.button(mask, down)
        if (expectPanel) {
            await("Native mouse $button/$down delivery") { (mouseDeliveries[binding]?.count ?: 0) > before }
            val receipt = checkNotNull(mouseDeliveries[binding])
            inputTimings.add("$currentCase\tmouse-$button\tOS\t$down\t${(receipt.nanos - began) / 1e6}")
        }
    }

    private fun click(
        id: String,
        button: Int = InputEvent.BUTTON1_DOWN_MASK,
        hold: Boolean = false,
    ) {
        val point = actionPoint(id)
        pointer.move(point.x, point.y)
        mouseButton(button, true)
        try {
            if (hold) {
                delay(280)
                snap("mouse-button-held")
            }
        } finally {
            mouseButton(button, false)
        }
        delay(70)
    }

    private fun actionPoint(id: String): java.awt.Point =
        edt {
            panel.rebuildActions()
            val bounds = panel.actions.single { it.id == id }.bounds
            val scale = minOf(panel.width / 1152.0, panel.height / 648.0)
            val p = panel.locationOnScreen
            java.awt.Point(
                (p.x + (panel.width - 1152 * scale) / 2 + bounds.centerX * scale).toInt(),
                (
                    p.y +
                        (panel.height - 648 * scale) / 2 +
                        bounds.centerY * scale
                ).toInt(),
            )
        }

    private fun focus(id: String) {
        repeat(32) {
            if (edt { panel.actions.getOrNull(panel.focusIndex)?.id == id }) return
            tap(KeyEvent.VK_TAB)
        }
        error("Cannot reach $id with Tab")
    }

    private fun reveal(id: String) {
        repeat(4) {
            if (edt { panel.actions.any { it.id == id } }) return
            focus("armor-down")
            activate("Return")
        }
        error("Cannot reveal armor $id")
    }

    private fun focused() = edt { panel.actions[panel.focusIndex].id }

    private fun foxCenter(image: BufferedImage) = FoxPixels.center(image)

    private fun directionCases() {
        for (scrolling in listOf(false, true)) {
            for ((key, sign) in directions) {
                case(
                    KeyEvent.getKeyText(key) + if (scrolling) " with scrolling camera" else "",
                    GameState.PLAYING,
                    "Fox moves screen-${if (sign < 0) "left" else "right"}, faces that way, then stops after release",
                ) {
                    if (scrolling) {
                        edt {
                            val x = if (sign > 0) 680.0 else 800.0
                            panel.game.player.reset(Vec(x, 536.0))
                            panel.game.cameraX = x - 380
                        }
                    }

                    fun interior(): Boolean {
                        val game = panel.game
                        return game.state == GameState.PLAYING && game.player.x > 40 && game.player.x < game.level.width - 40
                    }
                    val before = foxCenter(snap("direction-start"))
                    down(key)
                    val after =
                        try {
                            delay(210)
                            val position = foxCenter(snap("direction-held"))
                            check(edt { interior() && abs(panel.game.player.vx) > 1 }) {
                                "Capture overrun or blocked movement: release/braking needs a moving fox away from world boundaries"
                            }
                            position
                        } finally {
                            // A failed capture must release before case() takes another failure screenshot.
                            up(key)
                        }
                    await("Movement stops after release") { edt { abs(panel.game.player.vx) < .01 } }
                    check(edt { interior() }) { "Movement reached a wall or left gameplay before braking could be observed" }
                    snap("direction-released")
                    check((after.first - before.first) * sign > if (scrolling) 4 else 20) {
                        "Rendered direction was ${after.first - before.first}, expected sign $sign"
                    }
                    check(edt { abs(panel.game.player.vx) < .01 && panel.game.player.facing == sign })
                }
            }
        }
        for ((left, right) in listOf(
            KeyEvent.VK_A to KeyEvent.VK_D,
            KeyEvent.VK_LEFT to KeyEvent.VK_RIGHT,
            KeyEvent.VK_A to KeyEvent.VK_RIGHT,
            KeyEvent.VK_LEFT to KeyEvent.VK_D,
        )) {
            case(
                "${KeyEvent.getKeyText(left)} + ${KeyEvent.getKeyText(right)}",
                GameState.PLAYING,
                "Opposing controls cancel; releasing left leaves rightward movement",
            ) {
                val before = foxCenter(snap("opposed-start")).first
                val leftName = if (left == KeyEvent.VK_A) "a" else "left"
                val rightName = if (right == KeyEvent.VK_D) "d" else "right"
                physical(leftName to true, rightName to true)
                delay(200)
                check(abs(foxCenter(snap("opposed-held")).first - before) < 12)
                physical(leftName to false)
                delay(170)
                check(foxCenter(snap("opposed-release-left")).first > before + 15)
                physical(rightName to false)
            }
        }
        for ((first, second, sign) in listOf(
            Triple(KeyEvent.VK_A, KeyEvent.VK_LEFT, -1),
            Triple(KeyEvent.VK_D, KeyEvent.VK_RIGHT, 1),
        )) {
            case(
                "${KeyEvent.getKeyText(first)} + ${KeyEvent.getKeyText(second)} release",
                GameState.PLAYING,
                "Releasing one alternate movement key keeps moving until the remaining key is released",
            ) {
                down(first)
                down(second)
                delay(120)
                val held = foxCenter(snap("alternate-directions-held")).first
                up(first)
                delay(120)
                val remaining = foxCenter(snap("alternate-one-released")).first
                check((remaining - held) * sign > 15)
                up(second)
                delay(180)
                snap("alternate-both-released")
                check(edt { abs(panel.game.player.vx) < .01 })
            }
        }
    }

    private fun jumpCases() {
        for (key in jumpKeys) {
            case(KeyEvent.getKeyText(key), GameState.PLAYING, "Rise, hold, release-cut, double jump, reject third jump, land and recover") {
                val groundY = foxCenter(snap("jump-ground")).second
                down(key)
                delay(130)
                check(foxCenter(snap("jump-held")).second < groundY - 30)
                up(key)
                delay(60)
                snap("jump-released")
                down(key)
                delay(40)
                check(edt { panel.game.player.jumpsLeft == 0 && panel.game.player.vy < 0 })
                snap("jump-second")
                up(key)
                tap(key)
                snap("jump-third-rejected") { check(panel.game.player.jumpsLeft == 0) }
                delay(1100)
                snap("jump-landed")
                check(edt { panel.game.player.grounded && panel.game.player.jumpsLeft == 2 })
                down(key)
                delay(1500)
                snap("jump-held-through-landing")
                check(edt { panel.game.player.grounded && panel.game.player.jumpsLeft == 2 })
                up(key)
            }
        }
        case("Space + W + Up releases", GameState.PLAYING, "Alternate held jump keys form one jump; only releasing every key cuts it") {
            physical("space" to true, "w" to true, "up" to true)
            delay(70)
            snap("jump-three-bindings")
            check(edt { panel.game.player.jumpsLeft == 1 })
            physical("space" to false, "w" to false)
            snap("jump-up-still-held")
            check(edt { panel.game.player.jumpsLeft == 1 })
            physical("up" to false, "space" to true)
            await("Alternate jump is consumed") { edt { panel.game.player.jumpsLeft == 0 } }
            snap("jump-alternate-repress") { check(panel.game.player.jumpsLeft == 0) }
            physical("space" to false)
        }
    }

    private fun gentleCameraDirections() {
        for ((key, sign) in directions) {
            case(
                "${KeyEvent.getKeyText(key)} / Gentle camera",
                GameState.PLAYING,
                "The camera anchors the fox while scenery moves opposite the requested world direction; release stops movement",
            ) {
                edt {
                    val x = if (sign > 0) 3510.0 else 3600.0
                    panel.game.player.reset(Vec(x, 536.0))
                    panel.game.cameraX = x - 380
                }
                tap(KeyEvent.VK_ESCAPE)
                click("motion")
                snap("gentle-camera-setting")
                tap(KeyEvent.VK_ESCAPE)
                // Warm the original middle clearing before measuring its interior camera tracking.
                delay(250)

                fun spikeEdge(image: BufferedImage): Int {
                    // The first visible salmon spike-base strip is an independent world landmark.
                    val edge =
                        (0 until image.width).firstOrNull { x ->
                            (530..535).any { y -> (image.getRGB(x, y) and 0xffffff) == 0xe2987f }
                        }
                    return checkNotNull(edge) { "World landmark is not visible" }
                }
                val before = snap("gentle-camera-before")
                down(key)
                delay(140)
                val during = snap("gentle-camera-held")
                check(abs(foxCenter(during).first - foxCenter(before).first) < 20) { "Gentle camera did not anchor the fox" }
                check((spikeEdge(during) - spikeEdge(before)) * sign < -15) { "Scenery moved in the wrong direction" }
                up(key)
                await("Gentle movement stops after release") { edt { abs(panel.game.player.vx) < .01 } }
                snap("gentle-camera-released")
                check(edt { panel.game.state == GameState.PLAYING && panel.game.deaths == 0 && panel.game.player.facing == sign })
            }
        }
    }

    private fun gentleMotionPresentation() {
        case(
            "Gentle motion / visible bat wings",
            GameState.PLAYING,
            "The menu toggle freezes decorative wing motion after resume; turning it off restores visible animation",
        ) {
            // Hold the original species' patrol still to isolate decorative motion from its collision path.
            edt {
                panel.game.level.critters
                    .add(Critter(CritterDef("bat", Vec(430.0, 350.0), 0.0, 0.0)))
            }

            fun wingMask(label: String): BooleanArray {
                val image = snap(label)
                return BooleanArray(100 * 100) { i ->
                    (image.getRGB(380 + i % 100, 240 + i / 100) and 0xffffff) == 0xa58ed4
                }
            }
            val movingBefore = wingMask("wings-moving-before")
            delay(130)
            val movingAfter = wingMask("wings-moving-after")
            check(movingBefore.any { it } && !movingBefore.contentEquals(movingAfter))
            tap(KeyEvent.VK_ESCAPE)
            click("motion")
            snap("gentle-selected")
            tap(KeyEvent.VK_ESCAPE)
            val stillBefore = wingMask("wings-gentle-before")
            delay(180)
            val stillAfter = wingMask("wings-gentle-after")
            check(stillBefore.any { it } && stillBefore.contentEquals(stillAfter))
            tap(KeyEvent.VK_ESCAPE)
            click("motion")
            tap(KeyEvent.VK_ESCAPE)
            val restoredBefore = wingMask("wings-restored-before")
            delay(130)
            val restoredAfter = wingMask("wings-restored-after")
            check(!restoredBefore.contentEquals(restoredAfter))
        }
    }

    private fun motionSetting(
        state: GameState,
        activateSetting: (Boolean) -> Unit,
    ) {
        check(edt { !panel.settings.gentle && !panel.game.reducedMotion })
        activateSetting(true)
        snap("motion-setting-enabled")
        check(edt { panel.settings.gentle && panel.game.reducedMotion })
        motionEffect(state, frozen = true)
        activateSetting(false)
        snap("motion-setting-disabled")
        check(edt { !panel.settings.gentle && !panel.game.reducedMotion })
        motionEffect(state, frozen = false)
    }

    private fun motionEffect(
        state: GameState,
        frozen: Boolean,
    ) {
        click(if (state == GameState.TITLE) "start" else "resume")
        await("Motion setting enters actual gameplay") { edt { panel.game.state == GameState.PLAYING } }
        // Only the observer's patrol is stationary; the original bat art animates at the real game age.
        val observer = Critter(CritterDef("bat", Vec(430.0, 350.0), 0.0, 0.0))
        edt {
            panel.game.level.critters
                .add(observer)
        }

        fun wings(label: String): BooleanArray {
            val image = snap(label)
            return BooleanArray(100 * 100) { index ->
                (image.getRGB(380 + index % 100, 240 + index / 100) and 0xffffff) == 0xa58ed4
            }
        }
        try {
            val before = wings(if (frozen) "binding-wings-frozen-before" else "binding-wings-animated-before")
            check(before.any { it }) { "Original bat wings are not visibly present" }
            if (frozen) {
                delay(180)
                val after = wings("binding-wings-frozen-after")
                check(before.contentEquals(after)) { "This Gentle-motion binding did not freeze the visible bat wings" }
            } else {
                await("This binding restores visible bat animation") {
                    delay(80)
                    !before.contentEquals(wings("binding-wings-animated-after"))
                }
            }
        } finally {
            edt {
                panel.game.level.critters
                    .remove(observer)
            }
        }
        tap(KeyEvent.VK_ESCAPE)
        check(edt { panel.game.state == GameState.PAUSED })
        if (state == GameState.TITLE) {
            // There is no return-to-title command. Restage only the menu for this row's second
            // physical activation, preserving the actual setting selected by its first activation.
            edt { panel.game.state = GameState.TITLE }
            await("Fixture restages TITLE after visible motion proof") { edt { observedDesktopState.get(panel) == GameState.TITLE } }
        }
        snap("motion-menu-returned")
    }

    private fun dashCases() {
        for (modifier in listOf("left-shift", "right-shift")) {
            for (direction in listOf(-1, 1)) {
                case(
                    "$modifier facing $direction",
                    GameState.PLAYING,
                    "Dash in visible facing direction once per held press; release permits another dash",
                ) {
                    // Stay left of the camera-follow anchor so screen displacement measures
                    // this dash directly, without a returning camera cancelling part of it.
                    edt { panel.game.player.reset(Vec(if (direction > 0) 140.0 else 350.0, 536.0)) }
                    if (direction < 0) {
                        tap(KeyEvent.VK_A)
                        delay(160)
                    }
                    val before = foxCenter(snap("dash-start")).first
                    physical(modifier to true)
                    delay(270)
                    val after = foxCenter(snap("dash-held")).first
                    check((after - before) * direction > 70)
                    val position = edt { panel.game.player.x }
                    delay(850)
                    snap("dash-no-auto-repeat")
                    check(abs(edt { panel.game.player.x } - position) < 2)
                    physical(modifier to false)
                    physical(modifier to true)
                    delay(140)
                    snap("dash-repressed")
                    physical(modifier to false)
                    check((edt { panel.game.player.x } - position) * direction > 70)
                    check(edt { panel.game.state == GameState.PLAYING && panel.game.deaths == 0 })
                }
            }
        }
        case(
            "Left Shift + Right Shift",
            GameState.PLAYING,
            "Second physical modifier does not cancel first; releases recover without stuck input",
        ) {
            physical("left-shift" to true, "right-shift" to true)
            delay(200)
            physical("left-shift" to false)
            delay(700)
            snap("right-shift-still-held")
            val x = edt { panel.game.player.x }
            delay(300)
            check(abs(edt { panel.game.player.x } - x) < 2)
            physical("right-shift" to false)
        }
        for (first in listOf("left-shift", "right-shift")) {
            for (direction in listOf(-1, 1)) {
                val second = if (first == "left-shift") "right-shift" else "left-shift"
                case(
                    "$first then $second after cooldown, facing $direction",
                    GameState.PLAYING,
                    "A second Shift cannot bypass the held logical dash; both must release before another dash",
                ) {
                    edt { panel.game.player.reset(Vec(if (direction > 0) 140.0 else 430.0, 536.0)) }
                    if (direction < 0) {
                        tap(KeyEvent.VK_A)
                        delay(160)
                    }
                    physical(first to true)
                    delay(900)
                    val before = edt { panel.game.player.x }
                    snap("first-shift-still-held")
                    physical(second to true)
                    delay(220)
                    snap("second-shift-after-cooldown")
                    check(abs(edt { panel.game.player.x } - before) < 2) { "Second physical Shift retriggered an already held dash" }
                    physical(second to false)
                    delay(160)
                    snap("opposite-shift-released-first-still-held")
                    check(abs(edt { panel.game.player.x } - before) < 2)
                    physical(second to true)
                    physical(first to false)
                    delay(160)
                    check(abs(edt { panel.game.player.x } - before) < 2)
                    physical(second to false)
                    physical(second to true)
                    delay(160)
                    snap("both-shifts-released-then-repressed")
                    check((edt { panel.game.player.x } - before) * direction > 70)
                    check(edt { panel.game.state == GameState.PLAYING && panel.game.deaths == 0 })
                    physical(second to false)
                }
            }
        }
    }

    private fun weaponCases() {
        for (item in Equipment.ITEMS.filter { it.category == "weapon" }) {
            case(
                "J / ${item.name}",
                GameState.PLAYING,
                "Selected weapon appears, fires once per hold, then fires again after release",
                true,
            ) {
                edt {
                    panel.game.equipment.equip(item.id, true)
                    panel.game.player.reset(Vec(300.0, 300.0))
                }
                snap("weapon-equipped")
                down(KeyEvent.VK_J)
                await("All ${item.name} projectiles spawn") { edt { panel.game.shots.size == item.angles.size } }
                snap("weapon-projectile")
                projectileTravel(item, "weapon-traveled")
                delay((item.range / item.speed * 1000 + 800).toInt())
                snap("weapon-held-no-repeat")
                check(edt { panel.game.shots.isEmpty() })
                up(KeyEvent.VK_J)
                await("Fox lands before the repeat-shot jump") { edt { panel.game.player.grounded } }
                down(KeyEvent.VK_SPACE)
                await("Repeat-shot jump clears the ground") { edt { panel.game.player.y < 450 } }
                tap(KeyEvent.VK_J)
                await("All ${item.name} projectiles respawn after release") { edt { panel.game.shots.size == item.angles.size } }
                snap("weapon-repress")
                projectileTravel(item, "weapon-repress-traveled")
                up(KeyEvent.VK_SPACE)
            }
        }
        case("J locked", GameState.PLAYING, "Before bow reward, J creates no weapon or projectile") {
            tap(KeyEvent.VK_J)
            check(edt { panel.game.shots.isEmpty() })
        }
        case("J unequipped", GameState.PLAYING, "Turning weapon off prevents firing and HUD says off", true) {
            tap(KeyEvent.VK_ESCAPE)
            focus("bow")
            activate("Return")
            tap(KeyEvent.VK_ESCAPE)
            tap(KeyEvent.VK_J)
            check(
                edt {
                    panel.game.shots.isEmpty() &&
                        panel.game.equipment.weaponId
                            .isEmpty()
                },
            )
        }
    }

    private fun projectileTravel(
        item: Item,
        label: String,
    ) {
        await("${item.name} visibly separates from the fox") {
            edt {
                val shots = panel.game.shots
                shots.size == item.angles.size &&
                    shots.all {
                        !it.spent && it.x - panel.game.player.x >= 110 && it.y in 40.0..560.0
                    }
            }
        }
        // Even the longest spear shaft is now separate from the held weapon and fox.
        snap(label)
    }

    private fun combinations() {
        for (jump in listOf("space", "w", "up")) {
            for (shift in listOf("left-shift", "right-shift")) {
                case("$jump + $shift", GameState.PLAYING, "Simultaneous jump/dash produces a jump without spending the dash") {
                    val before = foxCenter(snap("jump-dash-start")).first
                    physical(jump to true, shift to true)
                    delay(100)
                    val after = foxCenter(snap("jump-dash-together")).first
                    check(abs(after - before) < 12) { "Simultaneous jump also dashed horizontally" }
                    check(edt { panel.game.player.y < 510 && panel.game.player.jumpsLeft == 1 && panel.game.player.dashCooldown == 0.0 })
                    physical(jump to false, shift to false)
                }
            }
        }
        for ((key, sign) in listOf("a" to -1, "left" to -1, "d" to 1, "right" to 1)) {
            case(
                "$key + J",
                GameState.PLAYING,
                "Turning and firing together sends the visible projectile in the new facing direction",
                true,
            ) {
                physical(key to true, "j" to true)
                delay(70)
                snap("turn-shot") {
                    check(
                        panel.game.shots.isNotEmpty() &&
                            panel.game.shots.all { it.direction == sign } &&
                            panel.game.player.facing == sign,
                    )
                }
                physical(key to false, "j" to false)
            }
            case("$key + Space + Shift", GameState.PLAYING, "Movement, jump and air dash remain responsive; release stops movement") {
                edt { panel.game.player.reset(Vec(if (sign > 0) 140.0 else 430.0, 536.0)) }
                await("Relocated movement fixture is grounded") { edt { panel.game.player.grounded } }
                physical(key to true, "space" to true)
                delay(100)
                snap("moving-jump") { check(panel.game.player.jumpsLeft == 1 && panel.game.player.y < 510) }
                physical("space" to false, "left-shift" to true)
                delay(130)
                snap("moving-air-dash") { check(panel.game.player.y < 510 && panel.game.player.facing == sign) }
                physical(key to false, "left-shift" to false)
            }
        }
    }

    private fun menuNavigation() {
        for (state in menus) {
            for (binding in listOf("Tab", "Left Shift+Tab", "Right Shift+Tab", "Down", "Up")) {
                case(binding, state, "Focus moves among enabled actions and wraps back to its starting action", true) {
                    val first = focused()
                    val count = edt { panel.actions.count { it.enabled } }
                    if (binding == "Left Shift+Tab") down(KeyEvent.VK_SHIFT)
                    if (binding == "Right Shift+Tab") physical("right-shift" to true)
                    repeat(count) { index ->
                        val key =
                            when (binding) {
                                "Down" -> KeyEvent.VK_DOWN
                                "Up" -> KeyEvent.VK_UP
                                else -> KeyEvent.VK_TAB
                            }
                        if (index == 0) {
                            down(key)
                            delay(170)
                            val heldFocus = focused()
                            snap("menu-navigation-held")
                            delay(650)
                            check(focused() == heldFocus) { "Held navigation repeated without release" }
                            up(key)
                        } else {
                            tap(key)
                        }
                        check(edt { panel.actions[panel.focusIndex].enabled })
                        if (index == 0) {
                            snap("menu-focus-step")
                            if (count > 1) check(focused() != first)
                        }
                    }
                    snap("menu-focus-wrap")
                    check(focused() == first)
                    releaseAll()
                }
            }
        }
        case("Tab held", GameState.TITLE, "Holding navigation advances exactly one action, with no native-repeat runaway") {
            down(KeyEvent.VK_TAB)
            delay(200)
            val selected = focused()
            snap("tab-held")
            delay(900)
            check(focused() == selected)
            up(KeyEvent.VK_TAB)
            tap(KeyEvent.VK_TAB)
            check(focused() != selected)
        }
    }

    private fun menuActivation() {
        for (state in menus) {
            for (key in activationKeys) {
                case(key, state, "Activate the focused Start/Resume/Continue/Replay action, without an accidental gameplay jump", true) {
                    activate(key, hold = true)
                    snap("menu-activated")
                    check(edt { panel.game.state == GameState.PLAYING && panel.game.player.jumpsLeft == 2 })
                }
            }
        }
        for (key in activationKeys) {
            case("$key / Restart all", GameState.PAUSED, "Restart returns to level one and clears equipment/progress", true) {
                focus("restart")
                snap("restart-focused")
                activate(key, hold = true)
                check(
                    edt {
                        panel.game.state == GameState.PLAYING &&
                            panel.game.stageIndex == 0 &&
                            panel.game.equipment.unlocked
                                .isEmpty()
                    },
                )
            }
        }
        case("Space held through Start", GameState.TITLE, "Held activation cannot turn into an automatic jump when the run begins") {
            down(KeyEvent.VK_SPACE)
            delay(1100)
            snap("start-space-held")
            check(edt { panel.game.state == GameState.PLAYING && panel.game.player.grounded && panel.game.player.jumpsLeft == 2 })
            up(KeyEvent.VK_SPACE)
            tap(KeyEvent.VK_SPACE)
            snap("start-space-repressed")
            check(edt { panel.game.player.y < 530 })
        }
    }

    private fun gearAndSettings() {
        for (key in activationKeys) {
            for (item in Equipment.ITEMS) {
                case(
                    "$key / ${item.name}",
                    GameState.PAUSED,
                    "Keyboard selection visibly toggles this item; a second activation toggles it off (or back on if initially selected)",
                    true,
                ) {
                    reveal(item.id)
                    focus(item.id)
                    snap("gear-focused")
                    val selected = edt { panel.game.equipment.isEquipped(item.id) }
                    activate(key, hold = true)
                    snap("gear-toggled")
                    check(edt { panel.game.equipment.isEquipped(item.id) != selected })
                    activate(key)
                    check(edt { panel.game.equipment.isEquipped(item.id) == selected })
                }
            }
        }
        for (state in listOf(GameState.TITLE, GameState.PAUSED)) {
            for (key in activationKeys) {
                for (id in listOf("sound", "motion")) {
                    val expected =
                        if (id == "motion") {
                            "This binding toggles Gentle motion; gameplay wings visibly freeze, " +
                                "then animate after the same binding restores it"
                        } else {
                            "Focused setting changes its visible on/off label and restores on second activation"
                        }
                    case("$key / $id", state, expected, true) {
                        if (id == "motion") {
                            motionSetting(state) { hold ->
                                focus(id)
                                snap("setting-focused")
                                activate(key, hold)
                            }
                        } else {
                            focus(id)
                            snap("setting-focused")
                            val previous = edt { panel.settings.muted }
                            activate(key, hold = true)
                            snap("setting-toggled")
                            check(edt { panel.settings.muted != previous })
                            activate(key)
                            check(edt { panel.settings.muted == previous })
                        }
                    }
                }
            }
        }
        for (key in activationKeys) {
            case(
                "$key / More and Previous armor",
                GameState.PAUSED,
                "Keyboard armor navigation reaches the last armor and returns to the first",
                true,
            ) {
                focus("armor-down")
                repeat(3) { activate(key, hold = it == 0) }
                snap("armor-last-page")
                check(edt { panel.actions.any { it.id == "sunleaf_armor" } })
                focus("armor-up")
                repeat(3) { activate(key, hold = it == 0) }
                snap("armor-first-page")
                check(edt { panel.actions.any { it.id == "armor" } })
            }
        }
    }

    private fun pauseAndRetry() {
        for (key in listOf(KeyEvent.VK_ESCAPE, KeyEvent.VK_P)) {
            for (state in listOf(GameState.PLAYING, GameState.RESPAWNING)) {
                case(KeyEvent.getKeyText(key), state, "Pause freezes the run/retry and the second press resumes exactly that state") {
                    tap(key)
                    snap("paused")
                    check(edt { panel.game.state == GameState.PAUSED })
                    val age = edt { panel.game.level.age }
                    val retry = edt { panel.game.respawnLeft }
                    down(key)
                    delay(1000)
                    snap("resume-held")
                    check(edt { panel.game.state == state })
                    up(key)
                    tap(key)
                    delay(200)
                    check(edt { panel.game.state == GameState.PAUSED })
                    val stopped = edt { panel.game.level.age }
                    delay(200)
                    check(edt { panel.game.level.age == stopped })
                    if (state == GameState.RESPAWNING) check(edt { panel.game.respawnLeft < retry }) else check(stopped >= age)
                }
            }
        }
        case(
            "R hold/release/retry",
            GameState.PLAYING,
            "One retry per held press, visible hurt, return to camp, then another retry after release",
        ) {
            down(KeyEvent.VK_R)
            delay(100)
            snap("retry-hurt")
            check(edt { panel.game.state == GameState.RESPAWNING && panel.game.deaths == 1 })
            delay(1200)
            snap("retry-return-held")
            check(edt { panel.game.state == GameState.PLAYING && panel.game.deaths == 1 && panel.game.player.x == 140.0 })
            up(KeyEvent.VK_R)
            tap(KeyEvent.VK_R)
            check(edt { panel.game.deaths == 2 })
        }
        for (state in GameState.entries) {
            case("M", state, "Global sound toggles once per held press; second press restores it (actual output checked separately)") {
                val previous = edt { panel.settings.muted }
                down(KeyEvent.VK_M)
                delay(850)
                snap("mute-held")
                check(edt { panel.settings.muted != previous && panel.audio.muted != previous })
                up(KeyEvent.VK_M)
                tap(KeyEvent.VK_M)
                check(edt { panel.settings.muted == previous })
            }
        }
    }

    private fun disabledCases() {
        val gameplayKeys = directions.map { it.first } + jumpKeys + listOf(KeyEvent.VK_SHIFT, KeyEvent.VK_J, KeyEvent.VK_R)
        for (state in menus + GameState.RESPAWNING) {
            for (key in gameplayKeys) {
                if (state in menus && key in listOf(KeyEvent.VK_SPACE, KeyEvent.VK_UP)) continue
                case(
                    KeyEvent.getKeyText(key) + " unavailable",
                    state,
                    "Unavailable gameplay command has no movement, shot, retry or state effect",
                ) {
                    val position = edt { panel.game.player.position }
                    down(key)
                    delay(150)
                    snap("unavailable-held")
                    up(key)
                    tap(key)
                    check(edt { panel.game.state == state && panel.game.player.position == position && panel.game.shots.isEmpty() })
                }
            }
        }
        for (state in GameState.entries) {
            if (state !=
                GameState.PLAYING
            ) {
                case("Right Shift unavailable", state, "Right modifier alone cannot dash or change menus outside gameplay") {
                    val position = edt { panel.game.player.position }
                    physical("right-shift" to true)
                    delay(150)
                    snap("right-shift-unavailable")
                    physical("right-shift" to false)
                    check(edt { panel.game.state == state && panel.game.player.position == position })
                }
            }
            if (state in listOf(GameState.PLAYING, GameState.RESPAWNING)) {
                for (key in listOf("Tab", "Down", "Return", "Keypad Enter")) {
                    case("$key unavailable", state, "Menu-only command cannot affect gameplay/retry") {
                        val position = edt { panel.game.player.position }
                        when (key) {
                            "Tab" -> tap(KeyEvent.VK_TAB)
                            "Down" -> tap(KeyEvent.VK_DOWN)
                            else -> activate(key)
                        }
                        check(edt { panel.game.state == state && panel.game.player.position == position })
                    }
                }
            }
            if (state in
                listOf(GameState.TITLE, GameState.CHAPTER_COMPLETE, GameState.WON)
            ) {
                for (key in listOf(KeyEvent.VK_ESCAPE, KeyEvent.VK_P)) {
                    case(KeyEvent.getKeyText(key) + " unavailable", state, "Pause shortcuts have no unintended effect in title/results") {
                        tap(key)
                        check(
                            edt {
                                panel.game.state ==
                                    state
                            },
                        )
                    }
                }
            }
        }
    }

    private fun mouseCases() {
        for (state in GameState.entries) {
            for ((name, button) in listOf(
                "Mouse left" to InputEvent.BUTTON1_DOWN_MASK,
                "Mouse middle" to InputEvent.BUTTON2_DOWN_MASK,
                "Mouse right" to InputEvent.BUTTON3_DOWN_MASK,
            )) {
                case(
                    name,
                    state,
                    if (button ==
                        InputEvent.BUTTON1_DOWN_MASK
                    ) {
                        "Primary menu/pause action activates"
                    } else {
                        "Nonprimary mouse button has no game/menu action"
                    },
                    true,
                ) {
                    val id =
                        when (state) {
                            GameState.TITLE -> "start"
                            GameState.PAUSED -> "resume"
                            GameState.CHAPTER_COMPLETE -> "continue"
                            GameState.WON -> "replay"
                            else -> "pause"
                        }
                    click(id, button, true)
                    val expected =
                        if (button !=
                            InputEvent.BUTTON1_DOWN_MASK
                        ) {
                            state
                        } else if (state in
                            listOf(GameState.PLAYING, GameState.RESPAWNING)
                        ) {
                            GameState.PAUSED
                        } else {
                            GameState.PLAYING
                        }
                    check(edt { panel.game.state == expected })
                }
            }
        }
        for (item in Equipment.ITEMS) {
            case("Mouse left / ${item.name}", GameState.PAUSED, "Click toggles the correct visible gear, then toggles it back", true) {
                reveal(item.id)
                val selected = edt { panel.game.equipment.isEquipped(item.id) }
                click(item.id, hold = true)
                snap("mouse-gear-toggle")
                check(edt { panel.game.equipment.isEquipped(item.id) != selected })
                click(item.id)
                check(edt { panel.game.equipment.isEquipped(item.id) == selected })
            }
        }
        for (state in listOf(GameState.TITLE, GameState.PAUSED)) {
            for (id in listOf("sound", "motion")) {
                val expected =
                    if (id == "motion") {
                        "This click toggles Gentle motion; gameplay wings visibly freeze, then animate after the same click restores it"
                    } else {
                        "Click changes the displayed setting and a second click restores it"
                    }
                case("Mouse left / $id", state, expected) {
                    if (id == "motion") {
                        motionSetting(state) { hold -> click(id, hold = hold) }
                    } else {
                        val before = edt { panel.settings.muted }
                        click(id, hold = true)
                        snap("mouse-setting-toggle")
                        check(edt { panel.settings.muted != before })
                        click(id)
                        check(edt { panel.settings.muted == before })
                    }
                }
            }
        }
        case("Mouse left / locked gear", GameState.PAUSED, "Clicking locked gear cannot equip it") {
            click("bow")
            check(
                edt {
                    panel.game.equipment.weaponId
                        .isEmpty()
                },
            )
        }
        case("Mouse left / Restart all", GameState.PAUSED, "Restart clears progress and gear", true) {
            click("restart")
            check(
                edt {
                    panel.game.state ==
                        GameState.PLAYING &&
                        panel.game.equipment.unlocked
                            .isEmpty()
                },
            )
        }
        case(
            "Mouse left / More and Previous armor",
            GameState.PAUSED,
            "Armor paging reaches both limits without losing keyboard focus",
            true,
        ) {
            repeat(3) { click("armor-down") }
            snap("mouse-last-armor")
            check(edt { panel.actions.any { it.id == "sunleaf_armor" } })
            repeat(3) { click("armor-up") }
            check(edt { panel.actions.any { it.id == "armor" } && panel.actions[panel.focusIndex].enabled })
        }
        for (state in GameState.entries) {
            for (rotation in listOf(-3, 3)) {
                case(
                    "Mouse wheel ${if (rotation < 0) "up" else "down"}",
                    state,
                    if (state ==
                        GameState.PAUSED
                    ) {
                        "Armor list scrolls within its limits"
                    } else {
                        "Scrolling does not affect game or menus"
                    },
                    true,
                ) {
                    if (state == GameState.PAUSED && rotation < 0) repeat(3) { click("armor-down") }
                    snap("wheel-ready")
                    val ids = edt { panel.actions.map { it.id } }
                    val point =
                        edt {
                            val p = panel.locationOnScreen
                            java.awt.Point(p.x + panel.width * 3 / 4, p.y + panel.height / 2)
                        }
                    pointer.move(point.x, point.y)
                    val beforeWheel = edt { wheelEvents }
                    val started = System.nanoTime()
                    // CRobot.m sends its argument directly as Quartz delta, whose positive sign
                    // means up; CPlatformResponder negates it for Java's down-positive rotation.
                    pointer.wheel(rotation)
                    await("Native wheel event") { edt { wheelEvents > beforeWheel } }
                    val actualRotation = edt { lastWheelRotation }
                    check(actualRotation * rotation > 0) { "Wheel direction: requested $rotation, delivered $actualRotation" }
                    inputTimings.add("$currentCase\tmouse-wheel\tOS\t$actualRotation\t${(System.nanoTime() - started) / 1e6}")
                    check(edt { panel.game.state == state })
                    if (state == GameState.PAUSED) {
                        check(edt { panel.actions.any { it.id == if (rotation < 0) "armor" else "sunleaf_armor" } })
                    } else {
                        check(edt { panel.actions.map { it.id } == ids })
                    }
                }
            }
        }
    }

    private fun focusCases() {
        val modifiers = listOf("left-shift", "right-shift")
        val ordinary = directions.map { it.first } + jumpKeys + KeyEvent.VK_J
        for (binding in ordinary.map { KeyEvent.getKeyText(it) } + modifiers) {
            case(
                "Release $binding while unfocused",
                GameState.PLAYING,
                "Focus loss pauses; release elsewhere then return cannot leave input stuck",
                true,
            ) {
                val key = ordinary.firstOrNull { KeyEvent.getKeyText(it) == binding }
                if (key != null) down(key) else physical(binding to true)
                delay(80)
                val other =
                    edt {
                        JFrame("Emberwood audit focus").apply {
                            setSize(240, 160)
                            setLocation(20, 20)
                            isVisible = true
                            toFront()
                            requestFocus()
                        }
                    }
                var registered = false
                try {
                    await("Auxiliary window receives focus") { edt { other.isFocused } }
                    pointer.registerAuxiliary(other.title)
                    registered = true
                    check(edt { panel.game.state == GameState.PAUSED }) { "OS focus change did not pause" }
                    if (key != null) up(key) else physical(binding to false)
                } finally {
                    try {
                        if (registered) pointer.unregisterAuxiliary(other.title)
                    } finally {
                        edt {
                            other.dispose()
                            frame.toFront()
                            panel.requestFocusInWindow()
                        }
                    }
                }
                await("Game window regains focus") { edt { frame.isFocused && panel.isFocusOwner } }
                snap("focus-return-paused")
                check(edt { panel.game.state == GameState.PAUSED })
                tap(KeyEvent.VK_ESCAPE)
                delay(1400)
                snap("focus-recovered")
                val x = edt { panel.game.player.x }
                delay(180)
                check(
                    edt {
                        panel.game.state == GameState.PLAYING &&
                            abs(panel.game.player.x - x) < .1 &&
                            panel.game.player.grounded &&
                            panel.game.shots.isEmpty()
                    },
                )
            }
        }
    }

    private fun mouseFocusCase() {
        case(
            "Release mouse left while unfocused",
            GameState.TITLE,
            "Mouse hold toggles once; focus loss clears hover/pressed styling; outside release cannot reactivate",
        ) {
            val blank =
                edt {
                    val origin = panel.locationOnScreen
                    java.awt.Point(origin.x + panel.width - 30, origin.y + 30)
                }
            pointer.move(blank.x, blank.y)
            val before = snap("mouse-focus-before").getRGB(366, 327)
            val muted = edt { panel.settings.muted }
            val point = actionPoint("sound")
            var other: JFrame? = null
            var registered = false
            var held = true
            pointer.move(point.x, point.y)
            mouseButton(InputEvent.BUTTON1_DOWN_MASK, true)
            try {
                snap("mouse-focus-held")
                check(edt { panel.settings.muted != muted })
                other =
                    edt {
                        JFrame("Emberwood mouse focus audit").apply {
                            setSize(240, 160)
                            // Leave the game's upper-left presentation marker and Sound button visible.
                            val origin = panel.locationOnScreen
                            setLocation(origin.x + panel.width - 240, origin.y + panel.height - 160)
                            isVisible = true
                            toFront()
                            requestFocus()
                        }
                    }
                await("Mouse-release target receives focus") { edt { other.isFocused } }
                pointer.registerAuxiliary(other.title)
                registered = true
                pointer.move(blank.x, blank.y)
                mouseButton(InputEvent.BUTTON1_DOWN_MASK, false)
                held = false
                snap("mouse-released-unfocused")
            } finally {
                try {
                    if (held) mouseButton(InputEvent.BUTTON1_DOWN_MASK, false)
                    if (registered) pointer.unregisterAuxiliary(checkNotNull(other).title)
                } finally {
                    edt {
                        other?.dispose()
                        frame.toFront()
                        panel.requestFocusInWindow()
                    }
                }
            }
            await("Game regains focus after mouse release") { edt { frame.isFocused && panel.isFocusOwner } }
            val after = snap("mouse-focus-recovered").getRGB(366, 327)
            check(after == before) { "A button retains stale hover/pressed styling after the pointer leaves during focus loss" }
            check(edt { panel.cursor.type == java.awt.Cursor.DEFAULT_CURSOR && panel.settings.muted != muted })
            click("sound")
            check(edt { panel.settings.muted == muted && panel.game.state == GameState.TITLE })
        }
    }

    private fun resizeAndClose(preferences: Path) {
        edt { frame.setSize(800, 600) }
        // Cocoa publishes the native size before Swing's panel layout. Waiting for
        // both prevents a filtered audit from cropping the preceding large frame.
        await("Small-window client layout") {
            edt {
                val insets = frame.insets
                frame.width == 800 &&
                    frame.height == 600 &&
                    panel.width == 800 - insets.left - insets.right &&
                    panel.height == 600 - insets.top - insets.bottom
            }
        }
        case(
            "Resize 800x600 / mouse Start",
            GameState.TITLE,
            "Letterboxed controls and text remain usable; click maps to the displayed button",
        ) {
            click("start")
            check(
                edt {
                    panel.game.state ==
                        GameState.PLAYING
                },
            )
        }
        case(
            "Resize 800x600 / gear and keyboard",
            GameState.PAUSED,
            "Small-window gear, settings, focus and hit targets remain readable and operable",
            true,
        ) {
            focus("bow")
            activate("Return")
            click("motion")
            snap("small-pause-gear")
            click("resume")
            check(
                edt {
                    panel.game.state ==
                        GameState.PLAYING
                },
            )
        }
        evidence.clear()
        snap("window-before-close")
        val muted = edt { panel.settings.muted }
        edt { frame.dispatchEvent(java.awt.event.WindowEvent(frame, java.awt.event.WindowEvent.WINDOW_CLOSING)) }
        delay(300)
        val closed = edt { !frame.isDisplayable }
        val persisted = Settings(preferences).muted == muted
        val result = if (closed && persisted) "PASS automatic" else "FAIL"
        rows.add(
            "Window lifecycle close (programmatic)\tALL\tWindow closes and preferences persist; physical close checked separately\t" +
                "$result\t${evidence.joinToString(", ")}",
        )
        if (!closed || !persisted) failures++
    }
}
