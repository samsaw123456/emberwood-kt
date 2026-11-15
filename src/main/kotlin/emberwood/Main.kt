package emberwood

import java.awt.Color
import java.awt.Dimension
import java.awt.Graphics
import java.awt.Graphics2D
import java.awt.RenderingHints
import java.awt.event.KeyAdapter
import java.awt.event.KeyEvent
import java.awt.event.MouseAdapter
import java.awt.event.MouseEvent
import java.awt.event.MouseMotionAdapter
import java.awt.event.WindowAdapter
import java.awt.event.WindowEvent
import java.awt.geom.Rectangle2D
import java.nio.file.Path
import javax.swing.JFrame
import javax.swing.JPanel
import javax.swing.SwingUtilities
import javax.swing.Timer
import kotlin.math.min

fun main(args: Array<String>) {
    if (args.contentEquals(arrayOf("--version"))) {
        println(
            "Emberwood Kotlin ${GamePanel::class.java.`package`.implementationVersion ?: "development"}; Java ${System.getProperty(
                "java.version",
            )}",
        )
        return
    }
    if (args.contentEquals(arrayOf("--help"))) {
        println("Emberwood Kotlin: launch with no arguments. Options: --version, --data-dir DIRECTORY.")
        return
    }
    if (args.isNotEmpty() && (args.size != 2 || args[0] != "--data-dir")) {
        System.err.println("Use no arguments to play, --version, --help, or --data-dir DIRECTORY.")
        kotlin.system.exitProcess(2)
    }
    if (java.awt.GraphicsEnvironment.isHeadless()) {
        System.err.println("Emberwood Kotlin needs a graphical desktop. Run the tests with ./gradlew check.")
        kotlin.system.exitProcess(2)
    }
    val dataIndex = args.indexOf("--data-dir")
    val directory =
        if (dataIndex >= 0) {
            require(dataIndex + 1 < args.size) { "--data-dir needs a directory" }
            Path.of(args[dataIndex + 1])
        } else {
            Settings.defaultDirectory()
        }
    SwingUtilities.invokeLater { openWindow(Settings(directory)) }
}

fun openWindow(settings: Settings): Pair<JFrame, GamePanel> {
    val panel = GamePanel(settings)
    val frame = JFrame("Emberwood Kotlin")
    frame.defaultCloseOperation = JFrame.DISPOSE_ON_CLOSE
    frame.contentPane = panel
    frame.iconImages = listOf(Assets.image("assets/app/emberwood.png"))
    frame.minimumSize = Dimension(800, 600)
    frame.pack()
    frame.setLocationRelativeTo(null)
    frame.addWindowFocusListener(
        object : WindowAdapter() {
            override fun windowLostFocus(event: WindowEvent) {
                panel.loseFocus()
            }

            override fun windowGainedFocus(event: WindowEvent) {
                panel.requestFocusInWindow()
            }
        },
    )
    frame.addWindowListener(
        object : WindowAdapter() {
            override fun windowClosed(event: WindowEvent) {
                panel.close()
            }
        },
    )
    frame.isVisible = true
    panel.requestFocusInWindow()
    return frame to panel
}

data class MenuAction(
    val id: String,
    val text: String,
    val bounds: Rectangle2D.Double,
    val enabled: Boolean = true,
    val activate: () -> Unit,
)

class GamePanel(
    val settings: Settings,
) : JPanel(),
    AutoCloseable {
    val game = Game()
    val audio = Audio()
    private val renderer = WorldRenderer()
    val actions = mutableListOf<MenuAction>()
    var focusIndex = 0
    private var gearScroll = 0
    private var hoverId: String? = null
    private var pressedId: String? = null
    private var lastAudioProblem: String? = null
    private val physical = mutableSetOf<Pair<Int, Int>>()
    private val held = mutableSetOf<Int>()
    private var jumpPress = false
    private var jumpRelease = false
    private var dashPress = false
    private var shootPress = false
    private var last = System.nanoTime()
    private var accumulator = 0.0
    private var previousState = game.state
    private val timer = Timer(16) { tick() }
    var paintedFrames = 0L
        private set
    var paintNanos = 0L
        private set

    init {
        preferredSize = Dimension(1152, 648)
        isFocusable = true
        focusTraversalKeysEnabled = false
        background = Color.BLACK
        game.reducedMotion = settings.gentle
        audio.muted = settings.muted
        addKeyListener(
            object : KeyAdapter() {
                override fun keyPressed(event: KeyEvent) {
                    press(event)
                }

                override fun keyReleased(event: KeyEvent) {
                    release(event)
                }
            },
        )
        addMouseListener(
            object : MouseAdapter() {
                override fun mousePressed(event: MouseEvent) {
                    requestFocusInWindow()
                    if (event.button != MouseEvent.BUTTON1) return
                    val (x, y) = logical(event.x, event.y)
                    rebuildActions()
                    val index = actions.indexOfFirst { it.enabled && it.bounds.contains(x, y) }
                    if (index >= 0) {
                        pressedId = actions[index].id
                        focusIndex = index
                        actions[index].activate()
                        transitioned()
                        repaint()
                    }
                }

                override fun mouseReleased(event: MouseEvent) {
                    pressedId = null
                    repaint()
                }

                override fun mouseExited(event: MouseEvent) {
                    hoverId = null
                    cursor = java.awt.Cursor.getDefaultCursor()
                    repaint()
                }
            },
        )
        addMouseMotionListener(
            object : MouseMotionAdapter() {
                override fun mouseMoved(event: MouseEvent) {
                    val (x, y) = logical(event.x, event.y)
                    val target = actions.firstOrNull { it.enabled && it.bounds.contains(x, y) }?.id
                    if (target !=
                        hoverId
                    ) {
                        hoverId = target
                        cursor =
                            java.awt.Cursor.getPredefinedCursor(
                                if (target ==
                                    null
                                ) {
                                    java.awt.Cursor.DEFAULT_CURSOR
                                } else {
                                    java.awt.Cursor.HAND_CURSOR
                                },
                            )
                        repaint()
                    }
                }
            },
        )
        addMouseWheelListener { event ->
            if (game.state ==
                GameState.PAUSED
            ) {
                gearScroll = (gearScroll + event.wheelRotation).coerceIn(0, 3)
                rebuildActions()
                repaint()
            }
        }
        timer.start()
    }

    private fun tick() {
        val endingWasAnimating = game.state == GameState.WON && game.particles.isNotEmpty()
        val now = System.nanoTime()
        accumulator += min((now - last) / 1e9, .133333333)
        last = now
        var first = true
        while (accumulator >= 1.0 / 60) {
            game.step(1.0 / 60, input(first))
            if (first) {
                jumpPress = false
                jumpRelease = false
                dashPress = false
                shootPress = false
            }
            first = false
            accumulator -= 1.0 / 60
        }
        game.drainSounds().forEach(audio::play)
        transitioned()
        if (game.state !in MENU_STATES || endingWasAnimating || lastAudioProblem != audio.unavailable) repaint()
        lastAudioProblem = audio.unavailable
    }

    private fun input(edges: Boolean) =
        InputFrame(
            left = KeyEvent.VK_A in held || KeyEvent.VK_LEFT in held,
            right = KeyEvent.VK_D in held || KeyEvent.VK_RIGHT in held,
            jumpHeld = jumping(),
            jumpPressed = edges && jumpPress,
            jumpReleased = edges && jumpRelease,
            dashHeld = KeyEvent.VK_SHIFT in held,
            dashPressed = edges && dashPress,
            shootPressed = edges && shootPress,
        )

    private fun jumping() = held.any { it in JUMP_KEYS }

    private fun press(event: KeyEvent) {
        val key = event.keyCode
        if (!physical.add(key to event.keyLocation)) return // Native auto-repeat cannot become a fresh jump/shot/menu action.
        if (key == KeyEvent.VK_M) {
            mute()
            return
        }
        if (key == KeyEvent.VK_ESCAPE || key == KeyEvent.VK_P) {
            when (game.state) {
                GameState.PLAYING, GameState.RESPAWNING -> {
                    game.pause()
                    audio.stop()
                }
                GameState.PAUSED -> game.resume()
                else -> Unit
            }
            transitioned()
            repaint()
            return
        }
        if (game.state in MENU_STATES) {
            rebuildActions()
            when (key) {
                KeyEvent.VK_TAB -> moveFocus(if (event.isShiftDown) -1 else 1)
                KeyEvent.VK_UP -> moveFocus(-1)
                KeyEvent.VK_DOWN -> moveFocus(1)
                KeyEvent.VK_ENTER, KeyEvent.VK_SPACE -> actions.getOrNull(focusIndex)?.takeIf { it.enabled }?.activate()
            }
            transitioned()
            repaint()
            return
        }
        if (game.state != GameState.PLAYING) return
        if (key == KeyEvent.VK_R) {
            game.retry()
            transitioned()
            return
        }
        val wasJumping = jumping()
        val wasDashing = KeyEvent.VK_SHIFT in held
        held.add(key)
        if (key in JUMP_KEYS && !wasJumping) jumpPress = true
        if (key == KeyEvent.VK_SHIFT && !wasDashing) dashPress = true
        if (key == KeyEvent.VK_J) shootPress = true
    }

    private fun release(event: KeyEvent) {
        physical.remove(event.keyCode to event.keyLocation)
        // macOS AWT reports only aggregate Shift transitions. If one Shift is
        // released while the other remains held, the final release may carry
        // the opposite location from the only press AWT delivered.
        if (event.keyCode == KeyEvent.VK_SHIFT && !event.isShiftDown && System.getProperty("os.name").startsWith("Mac")) {
            physical.removeAll { it.first == KeyEvent.VK_SHIFT }
        }
        val wasJumping = jumping()
        if (physical.none { it.first == event.keyCode }) held.remove(event.keyCode)
        if (wasJumping && !jumping()) jumpRelease = true
    }

    private fun clearInput() {
        held.clear()
        jumpPress = false
        jumpRelease = false
        dashPress = false
        shootPress = false
    }

    fun loseFocus() {
        hoverId = null
        pressedId = null
        cursor = java.awt.Cursor.getDefaultCursor()
        clearInput()
        physical.clear()
        game.pause()
        audio.stop()
        transitioned()
        repaint()
    }

    private fun transitioned() {
        if (game.state != previousState) {
            clearInput()
            focusIndex = 0
            val selectedArmor = Equipment.ITEMS.filter { it.category == "armor" }.indexOfFirst { it.id == game.equipment.armorId }
            gearScroll = if (game.state == GameState.PAUSED) (selectedArmor - 4).coerceIn(0, 3) else 0
            if (game.state == GameState.WON) {
                settings.best = game.elapsed
                settings.save()
            }
            previousState = game.state
            last = System.nanoTime()
            accumulator = 0.0
            repaint()
        }
        rebuildActions()
    }

    private fun moveFocus(direction: Int) {
        if (actions.isEmpty()) return
        repeat(actions.size) {
            focusIndex = Math.floorMod(focusIndex + direction, actions.size)
            if (actions[focusIndex].enabled) return
        }
    }

    private fun mute() {
        settings.muted = !settings.muted
        audio.muted = settings.muted
        settings.save("muted")
        if (!settings.muted) audio.play("gem")
        repaint()
    }

    private fun gentle() {
        settings.gentle = !settings.gentle
        game.reducedMotion = settings.gentle
        settings.save("gentle")
    }

    fun rebuildActions() {
        actions.clear()

        fun action(
            id: String,
            text: String,
            x: Double,
            y: Double,
            w: Double,
            h: Double = 38.0,
            enabled: Boolean = true,
            run: () -> Unit,
        ) {
            actions.add(MenuAction(id, text, Rectangle2D.Double(x, y, w, h), enabled, run))
        }

        fun settingsButtons(y: Double) {
            action(
                "sound",
                if (audio.unavailable !=
                    null
                ) {
                    "Sound unavailable"
                } else {
                    "Sound: ${if (settings.muted) "off" else "on"}"
                },
                360.0,
                y,
                210.0,
                run = ::mute,
            )
            action("motion", "Gentle motion: ${if (settings.gentle) "on" else "off"}", 582.0, y, 210.0, run = ::gentle)
        }
        when (game.state) {
            GameState.TITLE -> {
                action("start", "Start adventure", 456.0, 260.0, 240.0) { game.startRun() }
                settingsButtons(321.0)
            }
            GameState.PLAYING, GameState.RESPAWNING ->
                action("pause", "II", 1080.0, 16.0, 44.0, 42.0) {
                    game.pause()
                    audio.stop()
                }
            GameState.PAUSED -> {
                action("resume", "Resume", 132.0, 108.0, 430.0) { game.resume() }
                action("restart", "Restart all chapters", 590.0, 108.0, 430.0) { game.startRun() }
                val weapons = Equipment.ITEMS.filter { it.category == "weapon" }
                val armor = Equipment.ITEMS.filter { it.category == "armor" }
                for ((column, items) in listOf(weapons, armor).withIndex()) {
                    val visible = if (column == 1) items.drop(gearScroll).take(5) else items
                    for ((row, item) in visible.withIndex()) {
                        val unlocked = item.id in game.equipment.unlocked
                        val selected = game.equipment.isEquipped(item.id)
                        action(
                            item.id,
                            (if (selected) "✓ " else "") + item.name + (if (unlocked) "" else " (locked)"),
                            132.0 + column * 458,
                            194.0 + row * 59,
                            430.0,
                            32.0,
                            unlocked,
                        ) { game.toggleEquipment(item.id) }
                    }
                }
                action("armor-up", "Previous armor", 590.0, 492.0, 206.0, 30.0, gearScroll > 0) { gearScroll-- }
                action("armor-down", "More armor", 812.0, 492.0, 208.0, 30.0, gearScroll < 3) { gearScroll++ }
                settingsButtons(544.0)
            }
            GameState.CHAPTER_COMPLETE -> action("continue", "Continue", 416.0, 362.0, 320.0) { game.nextChapter() }
            GameState.WON -> action("replay", "Explore again", 416.0, 390.0, 320.0) { game.startRun() }
        }
        focusIndex = focusIndex.coerceIn(0, (actions.size - 1).coerceAtLeast(0))
        if (actions.getOrNull(focusIndex)?.enabled == false) moveFocus(1)
    }

    private fun logical(
        x: Int,
        y: Int,
    ): Pair<Double, Double> {
        val scale = min(width / 1152.0, height / 648.0)
        return (x - (width - 1152 * scale) / 2) / scale to (y - (height - 648 * scale) / 2) / scale
    }

    override fun paintComponent(graphics: Graphics) {
        super.paintComponent(graphics)
        val started = System.nanoTime()
        val g = graphics.create() as Graphics2D
        try {
            val scale = min(width / 1152.0, height / 648.0)
            g.translate((width - 1152 * scale) / 2, (height - 648 * scale) / 2)
            g.scale(scale, scale)
            g.clip(Rectangle2D.Double(0.0, 0.0, 1152.0, 648.0))
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_NEAREST_NEIGHBOR)
            renderer.draw(g, game)
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            drawHud(g)
            rebuildActions()
            if (game.state in MENU_STATES) drawMenu(g)
            for ((index, action) in actions.withIndex()) drawButton(g, action, index == focusIndex && game.state in MENU_STATES)
        } finally {
            g.dispose()
            paintedFrames++
            paintNanos += System.nanoTime() - started
        }
    }

    private fun text(
        g: Graphics2D,
        text: String,
        x: Int,
        y: Int,
        size: Int = 18,
        bold: Boolean = false,
        centered: Boolean = false,
    ) {
        g.font = (if (bold) Assets.bold else Assets.regular).deriveFont(size.toFloat())
        g.color = Color(243, 235, 205)
        val left = if (centered) x - g.fontMetrics.stringWidth(text) / 2 else x
        g.drawString(text, left, y)
    }

    private fun band(
        g: Graphics2D,
        x: Int,
        y: Int,
        w: Int,
        h: Int,
        alpha: Int = 205,
    ) {
        g.color = Color(18, 42, 42, alpha)
        g.fillRect(x, y, w, h)
    }

    private fun drawHud(g: Graphics2D) {
        if (game.state == GameState.TITLE) return
        band(g, 0, 0, 1152, 84, 190)
        text(g, "${game.stageIndex + 1}/20  ${game.level.title}", 24, 33, 22, true)
        text(
            g,
            game.level.sectionAt(game.player.x),
            24,
            67,
            15,
        )
        text(g, "Acorns ${game.level.takenAcorns.size}/3", 660, 38)
        text(g, "Gems ${game.level.takenGems.size}/${game.level.gems.size}", 814, 38)
        text(g, time(game.elapsed), 990, 38)
        val weapon = game.equipment.weapon?.name ?: if ("bow" in game.equipment.unlocked) "off" else "locked"
        val armor =
            game.equipment.armor?.let { "${it.name}: ${game.equipment.armorCharge}/${it.capacity}" }
                ?: if ("armor" in game.equipment.unlocked) "Armor: off" else "Armor: locked"
        text(g, "Dash: ${if (game.player.canDash) "ready" else "wait or land"}    J: $weapon    $armor", 420, 67, 15)
        band(g, 0, 588, 1152, 60)
        if (game.state !in MENU_STATES) {
            text(g, "A/D or ←/→: move    Space / W / ↑: jump twice    Shift: dash    J: weapon", 24, 611, 16)
            text(g, "R: retry    Esc / P: gear or pause    M: sound ${if (settings.muted) "off" else "on"}", 24, 637, 16)
            text(g, if (game.player.jumpsLeft > 0) "Air jump ready" else "Land to jump again", 920, 611, 15)
        }
        game.boss?.takeIf { it.engaged && !it.defeated }?.let { boss ->
            band(g, 244, 98, 664, 76)
            text(
                g,
                "${boss.name}: ${"●".repeat(boss.health)}${"○".repeat(3 - boss.health)}    Fox: ${"♥".repeat(game.playerHealth)}",
                576,
                126,
                20,
                centered = true,
            )
            text(g, boss.status, 576, 154, 16, centered = true)
        }
        if (game.messageLeft > 0 && game.state !in MENU_STATES) {
            band(g, 130, 538, 892, 46)
            text(g, game.message, 576, 566, 16, centered = true)
        }
    }

    private fun drawMenu(g: Graphics2D) {
        g.color = Color(12, 27, 30, if (game.state == GameState.TITLE) 115 else 180)
        g.fillRect(0, 0, 1152, 648)
        when (game.state) {
            GameState.TITLE -> {
                text(g, "Emberwood Kotlin", 576, 155, 38, true, true)
                text(g, "20 levels. Find three acorns in each.", 576, 203, 20, centered = true)
                text(g, "Earn weapons and armor at campfires.", 576, 231, 18, centered = true)
                if (settings.best > 0) text(g, "Best time: ${time(settings.best)}", 576, 392, 17, centered = true)
                band(g, 0, 562, 1152, 86)
                text(g, "A/D or ←/→: move    Space / W / ↑: jump twice    Shift: dash", 576, 590, 18, centered = true)
                text(g, "J: weapon after bow reward    R: retry    Esc/P: pause    M: sound", 576, 621, 17, centered = true)
            }
            GameState.PAUSED -> {
                band(g, 106, 30, 940, 572, 240)
                text(g, "Paused", 576, 77, 28, true, true)
                text(g, "Weapon", 132, 182, 18, true)
                text(g, "Armor   ${gearScroll + 1}–${gearScroll + 5} of 8", 590, 182, 18, true)
                text(g, "Choose one weapon and one armor. New camps and retries repair armor.", 576, 535, 13, centered = true)
                for ((column, items) in listOf(
                    Equipment.ITEMS.filter { it.category == "weapon" },
                    Equipment.ITEMS
                        .filter {
                            it.category ==
                                "armor"
                        }.drop(gearScroll)
                        .take(5),
                ).withIndex()) {
                    for ((row, item) in items.withIndex()) {
                        text(
                            g,
                            if (item.id in
                                game.equipment.unlocked
                            ) {
                                item.description
                            } else {
                                item.unlockHint
                            },
                            132 + column * 458,
                            244 + row * 59,
                            13,
                        )
                    }
                }
            }
            GameState.CHAPTER_COMPLETE -> {
                band(g, 316, 190, 520, 240, 240)
                text(g, "Level complete", 576, 236, 28, true, true)
                text(g, game.level.title, 576, 278, 21, centered = true)
                text(
                    g,
                    "Gems: ${game.level.takenGems.size} of ${game.level.gems.size}    Time: ${time(game.elapsed - game.chapterStartedAt)}",
                    576,
                    322,
                    18,
                    centered = true,
                )
                text(g, "Next: ${Levels.all[game.stageIndex + 1].title}", 576, 346, 15, centered = true)
            }
            GameState.WON -> {
                band(g, 286, 170, 580, 290, 240)
                text(g, "Heart of Emberwood reached!", 576, 220, 28, true, true)
                text(g, "Adventure complete", 576, 262, 21, centered = true)
                text(g, "Time: ${time(game.elapsed)}    Retries: ${game.deaths}", 576, 304, 19, centered = true)
                text(g, "Gems: ${game.collectedGems} / ${game.totalGems}", 576, 344, 19, centered = true)
                text(
                    g,
                    if (game.allSecrets) "All 20 fireflies found!" else "Hidden fireflies are still waiting to be found.",
                    576,
                    372,
                    16,
                    centered = true,
                )
            }
            else -> Unit
        }
        if (settings.problem != null) {
            text(
                g,
                "Couldn't read or save settings. You can still play.",
                576,
                if (game.state ==
                    GameState.TITLE
                ) {
                    535
                } else {
                    611
                },
                15,
                centered = true,
            )
        }
        val soundHint =
            if (game.state == GameState.CHAPTER_COMPLETE || game.state == GameState.WON) {
                "    M: sound ${if (settings.muted) "off" else "on"}"
            } else {
                ""
            }
        text(g, "Tab / Shift+Tab or ↑/↓: choose    Enter / Space: select$soundHint", 576, 638, 14, centered = true)
    }

    private fun drawButton(
        g: Graphics2D,
        action: MenuAction,
        focused: Boolean,
    ) {
        g.color =
            when {
                !action.enabled -> Color(39, 52, 48)
                action.id == pressedId -> Color(91, 103, 70)
                action.id == hoverId -> Color(74, 96, 73)
                else -> Color(57, 81, 64)
            }
        g.fill(action.bounds)
        if (focused) {
            g.color = Color(245, 206, 129)
            g.stroke = java.awt.BasicStroke(2f)
            g.draw(action.bounds)
        }
        g.font = Assets.regular.deriveFont(17f)
        g.color = if (action.enabled) Color(243, 235, 205) else Color(155, 165, 149)
        g.drawString(
            action.text,
            (action.bounds.centerX - g.fontMetrics.stringWidth(action.text) / 2).toFloat(),
            (action.bounds.centerY + 6).toFloat(),
        )
    }

    override fun close() {
        timer.stop()
        audio.close()
    }

    companion object {
        val MENU_STATES = setOf(GameState.TITLE, GameState.PAUSED, GameState.CHAPTER_COMPLETE, GameState.WON)
        val JUMP_KEYS = setOf(KeyEvent.VK_SPACE, KeyEvent.VK_W, KeyEvent.VK_UP)

        fun time(seconds: Double) = "%02d:%02d".format(seconds.toInt() / 60, seconds.toInt() % 60)
    }
}
