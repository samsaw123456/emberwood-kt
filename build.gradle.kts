plugins {
    kotlin("jvm") version "2.4.21"
    application
    id("org.jlleitschuh.gradle.ktlint") version "14.2.0"
}

group = "org.emberwood.kotlin"
version = file("VERSION").readText().trim()
repositories { mavenCentral() }

dependencies {
    testImplementation(kotlin("test-junit5"))
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

kotlin { jvmToolchain(25) }
application {
    mainClass.set("emberwood.MainKt")
    applicationDefaultJvmArgs = listOf("-Xms32m", "-Xmx256m", "--enable-native-access=ALL-UNNAMED")
}
tasks.test {
    useJUnitPlatform()
    jvmArgs("--enable-native-access=ALL-UNNAMED")
}
tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>().configureEach {
    compilerOptions { allWarningsAsErrors.set(true) }
}
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
tasks.register<Jar>("fatJar") {
    group = "build"
    archiveFileName.set("emberwood-kotlin.jar")
    manifest {
        attributes["Main-Class"] = application.mainClass.get()
        attributes["Implementation-Version"] = project.version
    }
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    from(sourceSets.main.get().output)
    dependsOn(configurations.runtimeClasspath)
    from({ configurations.runtimeClasspath.get().map { if (it.isDirectory) it else zipTree(it) } })
    exclude("META-INF/*.SF", "META-INF/*.RSA", "META-INF/*.DSA", "module-info.class")
}

tasks.register<JavaExec>("nativeAudit") {
    group = "verification"
    description = "Exercise every control through the native window and inspect resulting frames."
    dependsOn(tasks.testClasses)
    classpath = sourceSets.test.get().runtimeClasspath
    mainClass.set("emberwood.NativeAuditKt")
    javaLauncher.set(javaToolchains.launcherFor(java.toolchain))
    systemProperty(
        "audit.output",
        layout.buildDirectory
            .dir("audit")
            .get()
            .asFile.absolutePath,
    )
    systemProperty("java.awt.headless", "false")
    jvmArgs("-Xms32m", "-Xmx256m", "--enable-native-access=ALL-UNNAMED")
}
