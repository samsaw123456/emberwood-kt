// Test-only capture of one explicitly identified Emberwood fixture process.
// No microphone, whole-display audio filter, or system-mix fallback is used.
import AVFoundation
import CoreGraphics
import Darwin
import Foundation
import ScreenCaptureKit

enum CaptureFailure: Error, CustomStringConvertible {
    case unavailable(String)
    var description: String {
        switch self {
        case .unavailable(let message): return message
        }
    }
}

func verifyNativeFixture(_ appPath: String, pid: Int32) throws {
    let app = URL(fileURLWithPath: appPath).resolvingSymlinksInPath()
    let contents = app.appendingPathComponent("Contents")
    let metadata = try PropertyListSerialization.propertyList(
        from: Data(contentsOf: contents.appendingPathComponent("Info.plist")), format: nil)
    guard let info = metadata as? [String: Any],
          info["CFBundleIdentifier"] as? String == "org.emberwood.kotlin",
          info["CFBundleExecutable"] as? String == "Emberwood Kotlin" else {
        throw CaptureFailure.unavailable("Native capture target is not the isolated Emberwood app")
    }
    let executable = contents.appendingPathComponent("MacOS/Emberwood Kotlin").resolvingSymlinksInPath()
    let config = try String(contentsOf: contents.appendingPathComponent("app/Emberwood Kotlin.cfg"), encoding: .utf8)
    var section = ""
    var mains: [String] = []
    for raw in config.components(separatedBy: .newlines) {
        let line = raw.trimmingCharacters(in: .whitespaces)
        if line.hasPrefix("[") { section = line }
        if section == "[Application]", line.hasPrefix("app.mainclass=") {
            mains.append(String(line.dropFirst("app.mainclass=".count)))
        }
    }
    guard mains == ["emberwood.AudioStateFixture"] else {
        throw CaptureFailure.unavailable("Native capture target is not configured as the audio fixture")
    }
    // The native launcher embeds its main class in .cfg, not its argv. Recheck
    // kernel executable identity instead of weakening the fixture/PID boundary.
    guard let library = dlopen("/usr/lib/libproc.dylib", RTLD_NOW | RTLD_LOCAL) else {
        throw CaptureFailure.unavailable("Native process identity facility is unavailable")
    }
    defer { dlclose(library) }
    guard let symbol = dlsym(library, "proc_pidpath") else {
        throw CaptureFailure.unavailable("Native process identity function is unavailable")
    }
    typealias ProcessPath = @convention(c) (Int32, UnsafeMutableRawPointer?, UInt32) -> Int32
    let processPath = unsafeBitCast(symbol, to: ProcessPath.self)
    var bytes = [CChar](repeating: 0, count: 4096)
    let count = bytes.withUnsafeMutableBytes { processPath(pid, $0.baseAddress, UInt32($0.count)) }
    guard count > 0 else {
        throw CaptureFailure.unavailable("Native capture process executable is unavailable")
    }
    let path = String(decoding: bytes.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self)
    let actual = URL(fileURLWithPath: path).resolvingSymlinksInPath()
    guard actual == executable else {
        throw CaptureFailure.unavailable("Native capture PID does not match the exact launched executable")
    }
}

struct BufferTiming: Codable {
    let presentationSeconds: Double?
    let declaredFrames: Int
    let availableFrames: Int
    let retainedFrames: Int
    let pcmStartFrame: Int
    let sampleRate: Double
    let channels: UInt32
    let deltaFromExpectedSeconds: Double?
}

struct CaptureTiming: Codable {
    let bufferCount: Int
    let minimumBufferFrames: Int?
    let maximumBufferFrames: Int?
    let timestampGapCount: Int
    let timestampOverlapCount: Int
    let missingTimestampCount: Int
    let comparisonToleranceSeconds: Double
    let buffers: [BufferTiming]
}

final class AudioCapture: NSObject, SCStreamOutput, SCStreamDelegate {
    let queue = DispatchQueue(label: "org.emberwood.audio-audit")
    var samples: [Int16] = []
    var failure: String?
    var timings: [BufferTiming] = []
    var expectedPresentation: Double?
    let count = 96_000

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        queue.async { self.failure = error.localizedDescription }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer buffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, samples.count < count, failure == nil else { return }
        guard let description = CMSampleBufferGetFormatDescription(buffer),
              let format = CMAudioFormatDescriptionGetStreamBasicDescription(description) else {
            failure = "Captured audio has no PCM format"
            return
        }
        let info = format.pointee
        guard info.mFormatID == kAudioFormatLinearPCM,
              info.mFormatFlags & kAudioFormatFlagIsFloat != 0,
              info.mFormatFlags & kAudioFormatFlagIsBigEndian == 0,
              info.mBitsPerChannel == 32, info.mSampleRate == 48_000 else {
            failure = "Expected 48000 Hz Float32 process audio"
            return
        }
        var bytes = 0
        _ = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            buffer, bufferListSizeNeededOut: &bytes, bufferListOut: nil, bufferListSize: 0,
            blockBufferAllocator: nil, blockBufferMemoryAllocator: nil, flags: 0, blockBufferOut: nil)
        guard bytes >= MemoryLayout<AudioBufferList>.size else {
            failure = "Captured audio has no buffers"
            return
        }
        let storage = UnsafeMutableRawPointer.allocate(byteCount: bytes, alignment: 16)
        defer { storage.deallocate() }
        let list = storage.bindMemory(to: AudioBufferList.self, capacity: 1)
        var retained: CMBlockBuffer?
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            buffer, bufferListSizeNeededOut: nil, bufferListOut: list, bufferListSize: bytes,
            blockBufferAllocator: nil, blockBufferMemoryAllocator: nil,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment, blockBufferOut: &retained)
        guard status == noErr else {
            failure = "Audio buffer extraction failed: \(status)"
            return
        }
        withExtendedLifetime(retained) {
            let buffers = UnsafeMutableAudioBufferListPointer(list)
            guard let first = buffers.first, let data = first.mData, first.mNumberChannels > 0 else { return }
            let stride = Int(first.mNumberChannels)
            let available = Int(first.mDataByteSize) / MemoryLayout<Float>.size / stride
            let frames = min(available, count - samples.count)
            let declared = CMSampleBufferGetNumSamples(buffer)
            let pts = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(buffer))
            let timestamp = pts.isFinite ? pts : nil
            let delta = timestamp.flatMap { current in expectedPresentation.map { current - $0 } }
            timings.append(BufferTiming(
                presentationSeconds: timestamp, declaredFrames: declared,
                availableFrames: available, retainedFrames: frames, pcmStartFrame: samples.count,
                sampleRate: info.mSampleRate, channels: info.mChannelsPerFrame,
                deltaFromExpectedSeconds: delta))
            expectedPresentation = timestamp.map { $0 + Double(declared) / info.mSampleRate }
            let values = data.assumingMemoryBound(to: Float.self)
            for frame in 0..<frames {
                let value = values[frame * stride]
                guard value.isFinite else {
                    failure = "Captured audio contains a nonfinite sample"
                    return
                }
                samples.append(Int16((max(-1, min(1, value)) * 32767).rounded()))
            }
        }
    }

    func save(to url: URL) throws {
        var pcm: [Int16] = []
        var issue: String?
        var observed: [BufferTiming] = []
        queue.sync { pcm = samples; issue = failure; observed = timings }
        let tolerance = 0.5 / 48_000.0
        let timing = CaptureTiming(
            bufferCount: observed.count,
            minimumBufferFrames: observed.map(\.availableFrames).min(),
            maximumBufferFrames: observed.map(\.availableFrames).max(),
            timestampGapCount: observed.filter { ($0.deltaFromExpectedSeconds ?? 0) > tolerance }.count,
            timestampOverlapCount: observed.filter { ($0.deltaFromExpectedSeconds ?? 0) < -tolerance }.count,
            missingTimestampCount: observed.filter { $0.presentationSeconds == nil }.count,
            comparisonToleranceSeconds: tolerance, buffers: observed)
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(timing).write(
            to: url.deletingPathExtension().appendingPathExtension("timing.json"), options: .atomic)
        if let issue { throw CaptureFailure.unavailable(issue) }
        guard pcm.count == count else {
            throw CaptureFailure.unavailable("Only \(pcm.count) of \(count) PCM frames arrived; output remains unverified")
        }
        var wav = Data()
        func text(_ value: String) { wav.append(contentsOf: value.utf8) }
        func number<T: FixedWidthInteger>(_ value: T) {
            var little = value.littleEndian
            withUnsafeBytes(of: &little) { wav.append(contentsOf: $0) }
        }
        text("RIFF"); number(UInt32(36 + pcm.count * 2)); text("WAVEfmt ")
        number(UInt32(16)); number(UInt16(1)); number(UInt16(1))
        number(UInt32(48_000)); number(UInt32(96_000)); number(UInt16(2)); number(UInt16(16))
        text("data"); number(UInt32(pcm.count * 2))
        for sample in pcm { number(sample) }
        try wav.write(to: url, options: .atomic)
    }
}

@main
struct GameAudioCapture {
    static func main() async {
        do {
            let arguments = CommandLine.arguments
            if arguments.count == 4, arguments[1] == "--verify-native-fixture" {
                guard let pid = Int32(arguments[2]), pid > 1, pid != getpid() else {
                    throw CaptureFailure.unavailable("Invalid native fixture PID")
                }
                try verifyNativeFixture(arguments[3], pid: pid)
                print("PASS: exact native fixture identity; no capture or permission request")
                return
            }
            guard [3, 5].contains(arguments.count),
                  let pid = Int32(CommandLine.arguments[1]), pid > 1, pid != getpid() else {
                throw CaptureFailure.unavailable("Usage: mac-audio-capture GAME_FIXTURE_PID OUTPUT.wav [--native-fixture APP]")
            }
            let nativeFixture = arguments.count == 5
            if nativeFixture {
                guard arguments[3] == "--native-fixture" else {
                    throw CaptureFailure.unavailable("Unknown native capture option")
                }
                try verifyNativeFixture(arguments[4], pid: pid)
            }
            let check = Process()
            check.executableURL = URL(fileURLWithPath: "/bin/ps")
            check.arguments = ["-p", String(pid), "-o", "command="]
            let pipe = Pipe()
            check.standardOutput = pipe
            try check.run()
            let command = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            check.waitUntilExit()
            guard check.terminationStatus == 0,
                  nativeFixture || command.contains("emberwood.AudioStateFixture"),
                  command.contains("--data-dir") else {
                throw CaptureFailure.unavailable("Refusing to capture a process other than the explicitly launched Emberwood audio fixture")
            }
            guard CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess() else {
                throw CaptureFailure.unavailable("Normal macOS screen/audio consent was unavailable; no capture started")
            }
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: false)
            let matches = content.applications.filter { $0.processID == pid }
            guard matches.count == 1, let display = content.displays.first else {
                throw CaptureFailure.unavailable("The exact game process was not shareable; no broader capture was attempted")
            }
            let filter = SCContentFilter(display: display, including: matches, exceptingWindows: [])
            let configuration = SCStreamConfiguration()
            configuration.width = 2
            configuration.height = 2
            configuration.minimumFrameInterval = CMTime(value: 1, timescale: 1)
            configuration.showsCursor = false
            configuration.capturesAudio = true
            configuration.captureMicrophone = false
            configuration.excludesCurrentProcessAudio = true
            configuration.sampleRate = 48_000
            configuration.channelCount = 2
            let capture = AudioCapture()
            let stream = SCStream(filter: filter, configuration: configuration, delegate: capture)
            try stream.addStreamOutput(capture, type: .audio, sampleHandlerQueue: capture.queue)
            try await stream.startCapture()
            print("READY")
            fflush(stdout)
            try await Task.sleep(nanoseconds: 2_500_000_000)
            try await stream.stopCapture()
            try capture.save(to: URL(fileURLWithPath: CommandLine.arguments[2]))
            print("PASS: captured 96000 PCM frames from game PID \(pid) only")
        } catch {
            fputs("Emberwood audio capture unavailable: \(error)\n", stderr)
            exit(77)
        }
    }
}
