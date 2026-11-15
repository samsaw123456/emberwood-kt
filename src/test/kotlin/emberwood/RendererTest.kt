package emberwood

import java.awt.image.BufferedImage
import java.nio.file.Files
import java.nio.file.Path
import javax.imageio.ImageIO
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RendererTest {
    private val output = Path.of("build", "render-audit")

    private fun frame(game: Game): BufferedImage {
        val image = BufferedImage(1152, 648, BufferedImage.TYPE_INT_ARGB)
        val graphics = image.createGraphics()
        try {
            graphics.clipRect(0, 0, image.width, image.height)
            WorldRenderer().draw(graphics, game)
        } finally {
            graphics.dispose()
        }
        return image
    }

    @Test
    fun allOriginalRegionsAndGuardianResourcesRender() {
        Files.createDirectories(output)
        val themes = mutableSetOf<String>()
        for (chapter in 0 until 20) {
            val game = Game()
            game.loadChapter(chapter)
            val scene = frame(game)
            assertEquals(255, scene.getRGB(500, 200) ushr 24, "Every region paints an opaque scene")
            if (themes.add(game.level.theme)) ImageIO.write(scene, "png", output.resolve("region-${game.level.theme}.png").toFile())
            game.boss?.let {
                game.player.x = it.x - 170
                game.cameraX = it.x - 520
                ImageIO.write(frame(game), "png", output.resolve("boss-${it.species}.png").toFile())
            }
        }
        assertEquals(8, themes.size)
    }

    @Test
    fun wornEquipmentAndRegularMonstersHaveDistinctImages() {
        Files.createDirectories(output)
        val gearHashes = mutableSetOf<Int>()
        val game = Game()
        game.equipment.rewardsAt(19, 9)
        for (item in Equipment.ITEMS) {
            for (other in Equipment.ITEMS) game.equipment.equip(other.id, false)
            game.equipment.equip(item.id, true)
            val image = BufferedImage(150, 100, BufferedImage.TYPE_INT_ARGB)
            val graphics = image.createGraphics()
            graphics.translate(75.0 - game.player.x, 85.0 - game.player.y)
            ActorArt.fox(Art(graphics), game)
            graphics.dispose()
            gearHashes.add(image.getRGB(0, 0, 150, 100, null, 0, 150).contentHashCode())
            ImageIO.write(image, "png", output.resolve("gear-${item.id}.png").toFile())
        }
        assertEquals(13, gearHashes.size, "Each weapon and armor set has distinguishable visible equipment")
        val creatureHashes = mutableSetOf<Int>()
        for (species in listOf("opossum", "slime", "beetle", "bat")) {
            val image = BufferedImage(150, 120, BufferedImage.TYPE_INT_ARGB)
            val graphics = image.createGraphics()
            val critter = Critter(CritterDef(species, Vec(75.0, 100.0), 0.0, 1.0))
            ActorArt.critter(Art(graphics), critter, 0.3, false)
            graphics.dispose()
            creatureHashes.add(image.getRGB(0, 0, 150, 120, null, 0, 150).contentHashCode())
            ImageIO.write(image, "png", output.resolve("monster-$species.png").toFile())
        }
        assertEquals(4, creatureHashes.size)
    }

    @Test
    fun reducedMotionStopsDecorativeAnimation() {
        val critter = Critter(CritterDef("bat", Vec(75.0, 100.0), 0.0, 0.0))

        fun draw(
            time: Double,
            gentle: Boolean,
        ): IntArray {
            val image = BufferedImage(150, 120, BufferedImage.TYPE_INT_ARGB)
            val graphics = image.createGraphics()
            ActorArt.critter(Art(graphics), critter, time, gentle)
            graphics.dispose()
            return image.getRGB(0, 0, 150, 120, null, 0, 150)
        }
        assertTrue(draw(0.0, true).contentEquals(draw(0.7, true)))
        assertTrue(!draw(0.0, false).contentEquals(draw(0.7, false)))
    }
}
