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

final class AudioCapture: NSObject, SCStreamOutput, SCStreamDelegate {
    let queue = DispatchQueue(label: "org.emberwood.audio-audit")
    var samples: [Int16] = []
    var failure: String?
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
            let frames = min(Int(first.mDataByteSize) / MemoryLayout<Float>.size / stride, count - samples.count)
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
        queue.sync { pcm = samples; issue = failure }
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
            guard CommandLine.arguments.count == 3,
                  let pid = Int32(CommandLine.arguments[1]), pid > 1, pid != getpid() else {
                throw CaptureFailure.unavailable("Usage: mac-audio-capture GAME_FIXTURE_PID OUTPUT.wav")
            }
            let check = Process()
            check.executableURL = URL(fileURLWithPath: "/bin/ps")
            check.arguments = ["-p", String(pid), "-o", "command="]
            let pipe = Pipe()
            check.standardOutput = pipe
            try check.run()
            let command = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            check.waitUntilExit()
            guard check.terminationStatus == 0, command.contains("emberwood.AudioStateFixture"),
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
