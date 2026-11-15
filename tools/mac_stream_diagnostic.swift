// Opt-in evidence only; SCScreenshotManager still supplies audit screenshots.
// API basis: developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos
// The stream may perturb presentation. Only simultaneous disagreement isolates
// the snapshot path; disappearance of the symptom is merely non-reproduction.
import CoreGraphics
import CoreMedia
import CoreVideo
import Darwin
import Foundation
import ImageIO
import ScreenCaptureKit
import UniformTypeIdentifiers

struct StreamEvidenceLimits {
    static let seconds = 90.0
    static let records = 6000
    static let images = 128

    static func permits(elapsed: Double, count: Int) -> Bool {
        elapsed < seconds && count < records
    }
}

/// Read the existing monochrome nonce from BGRA pixels, accounting for the
/// title bar and logical-to-pixel scaling without assuming the capture scale.
func streamNonce(bytes: UnsafeRawPointer, width: Int, height: Int, rowBytes: Int,
                 window: CGRect, panel: CGRect) -> Int? {
    guard width > 0, height > 0, rowBytes >= width * 4,
          window.width > 0, window.height > 0, window.contains(panel) else { return nil }
    var nonce = 0
    for index in 0..<20 {
        let x = Int(((panel.minX - window.minX) + Double(9 + index % 4 * 3)) * Double(width) / window.width)
        let y = Int(((panel.minY - window.minY) + Double(9 + index / 4 * 3)) * Double(height) / window.height)
        guard x >= 0, y >= 0, x < width, y < height else { return nil }
        let pixel = bytes.advanced(by: y * rowBytes + x * 4).assumingMemoryBound(to: UInt8.self)
        let white: Bool
        if pixel[0] >= 224 && pixel[1] >= 224 && pixel[2] >= 224 { white = true }
        else if pixel[0] <= 31 && pixel[1] <= 31 && pixel[2] <= 31 { white = false }
        else { return nil }
        if index < 4 {
            guard white == (index % 2 == 0) else { return nil }
        } else if white { nonce |= 1 << (index - 4) }
    }
    return nonce
}

final class StreamDiagnostic: NSObject, SCStreamOutput, SCStreamDelegate {
    private let directory: URL
    private let pid: Int32
    private let callbackQueue = DispatchQueue(label: "emberwood.stream-evidence.callbacks")
    private let imageQueue = DispatchQueue(label: "emberwood.stream-evidence.images", qos: .utility)
    private let imageSlots = DispatchSemaphore(value: 2)
    private let imageLock = NSLock()
    private var writtenImages = 0
    private var imageErrors: [String] = []
    private var stream: SCStream?
    private var windowID: UInt32?
    private var windowRectangle = CGRect.zero
    private var panelRectangle: CGRect?
    private var startedHost = 0.0
    private var records: [[String: Any]] = []
    private var imageCount = 0
    private var skippedImages = 0
    private var droppedRecords = 0
    private var previousImageNonce: Int?
    private var previousImageHost = -Double.infinity
    private var errors: [String] = []
    private var stopped = false
    private var geometryChange: [String: Any]?

    init(directory: URL, pid: Int32) throws {
        self.directory = directory
        self.pid = pid
        super.init()
        let manager = FileManager.default
        if manager.fileExists(atPath: directory.path) {
            guard try manager.contentsOfDirectory(atPath: directory.path).isEmpty else {
                throw CaptureError.unavailable("Stream diagnostic directory must be empty")
            }
        } else { try manager.createDirectory(at: directory, withIntermediateDirectories: true) }
    }

    private static func hostSeconds() -> Double {
        CMTimeGetSeconds(CMClockGetTime(CMClockGetHostTimeClock()))
    }

    func observe(window: SCWindow, rectangle: [Int]?) async throws {
        guard window.owningApplication?.processID == pid,
              windowID == nil || windowID == window.windowID else {
            throw CaptureError.unavailable("The diagnostic cannot change its exact game window")
        }
        if stopped { return }
        if stream != nil, window.frame != windowRectangle {
            // The focused audit finally resizes before closing. End this fixed-
            // geometry segment without replacing the separate snapshot proof.
            callbackQueue.sync {
                geometryChange = ["receipt_host_seconds": Self.hostSeconds(),
                    "previous": [windowRectangle.minX, windowRectangle.minY, windowRectangle.width, windowRectangle.height],
                    "current": [window.frame.minX, window.frame.minY, window.frame.width, window.frame.height]]
                panelRectangle = nil
            }
            try await stopStream()
            return
        }
        if let rectangle {
            guard rectangle.count == 4 else { throw CaptureError.unavailable("Invalid stream panel rectangle") }
            let panel = CGRect(x: rectangle[0], y: rectangle[1], width: rectangle[2], height: rectangle[3])
            guard panel.width > 0, panel.height > 0, window.frame.contains(panel) else {
                throw CaptureError.unavailable("Stream panel rectangle is outside the game window")
            }
            callbackQueue.sync { panelRectangle = panel }
        }
        if stream != nil { return }
        windowID = window.windowID
        windowRectangle = window.frame
        startedHost = Self.hostSeconds()
        let config = SCStreamConfiguration()
        config.width = Int(window.frame.width.rounded())
        config.height = Int(window.frame.height.rounded())
        config.pixelFormat = kCVPixelFormatType_32BGRA
        config.minimumFrameInterval = CMTime(value: 1, timescale: 30)
        config.queueDepth = 3
        config.showsCursor = false
        config.ignoreShadowsSingleWindow = true
        config.capturesAudio = false
        config.captureMicrophone = false
        let newStream = SCStream(filter: SCContentFilter(desktopIndependentWindow: window), configuration: config, delegate: self)
        stream = newStream
        try newStream.addStreamOutput(self, type: .screen, sampleHandlerQueue: callbackQueue)
        try await newStream.startCapture()
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        callbackQueue.async { self.errors.append("SCStream stopped: \(error)") }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sample: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, !stopped else { return }
        receive(sample)
    }

    private func receive(_ sample: CMSampleBuffer) {
        let host = Self.hostSeconds()
        let mach = mach_absolute_time()
        let unix = Date().timeIntervalSince1970
        let machAfter = mach_absolute_time()
        let hostAfter = Self.hostSeconds()
        guard StreamEvidenceLimits.permits(elapsed: host - startedHost, count: records.count) else {
            droppedRecords += 1
            return
        }
        let attachments = (CMSampleBufferGetSampleAttachmentsArray(sample, createIfNecessary: false)
            as? [[SCStreamFrameInfo: Any]])?.first
        let status = attachments?[.status] as? Int
        let pts = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample))
        var record: [String: Any] = ["sequence": records.count, "receipt_host_seconds": host,
                                     "receipt_unix_seconds": unix, "receipt_host_after_seconds": hostAfter,
                                     "receipt_mach_ticks": mach, "receipt_mach_after_ticks": machAfter,
                                     "valid": sample.isValid, "status": NSNull(),
                                     "presentation_seconds": pts.isFinite ? pts as Any : NSNull(),
                                     "display_time": attachments?[.displayTime] ?? NSNull()]
        if let status { record["status"] = status }
        if let panel = panelRectangle { record["panel_rectangle"] = [panel.minX, panel.minY, panel.width, panel.height] }
        if sample.isValid, status == SCFrameStatus.complete.rawValue,
           let pixels = CMSampleBufferGetImageBuffer(sample) {
            record["width"] = CVPixelBufferGetWidth(pixels)
            record["height"] = CVPixelBufferGetHeight(pixels)
            inspect(pixels, host: host, record: &record)
        }
        records.append(record)
    }

    private func inspect(_ pixels: CVPixelBuffer, host: Double, record: inout [String: Any]) {
        guard CVPixelBufferGetPixelFormatType(pixels) == kCVPixelFormatType_32BGRA,
              CVPixelBufferLockBaseAddress(pixels, .readOnly) == kCVReturnSuccess else {
            errors.append("Cannot read BGRA stream pixels")
            return
        }
        defer { CVPixelBufferUnlockBaseAddress(pixels, .readOnly) }
        guard let bytes = CVPixelBufferGetBaseAddress(pixels) else { errors.append("Missing stream pixels"); return }
        let width = CVPixelBufferGetWidth(pixels), height = CVPixelBufferGetHeight(pixels)
        let rowBytes = CVPixelBufferGetBytesPerRow(pixels)
        let nonce = panelRectangle.flatMap {
            streamNonce(bytes: bytes, width: width, height: height, rowBytes: rowBytes, window: windowRectangle, panel: $0)
        }
        record["nonce"] = NSNull()
        if let nonce { record["nonce"] = nonce }
        guard nonce != previousImageNonce || host - previousImageHost >= 0.5 else { return }
        guard imageCount < StreamEvidenceLimits.images, imageSlots.wait(timeout: .now()) == .success else {
            skippedImages += 1
            return
        }
        // Copy out of the IOSurface before returning. PNG encoding never retains
        // a CVPixelBuffer or occupies one of the stream's three native slots.
        let copy = Data(bytes: bytes, count: rowBytes * height)
        let filename = String(format: "stream-%04d.png", imageCount)
        record["image"] = filename
        imageCount += 1
        previousImageHost = host
        previousImageNonce = nonce
        imageQueue.async {
            defer { self.imageSlots.signal() }
            do {
                try Self.writeImage(copy, width: width, height: height, rowBytes: rowBytes,
                                    to: self.directory.appendingPathComponent(filename))
                self.imageLock.lock(); self.writtenImages += 1; self.imageLock.unlock()
            } catch {
                self.imageLock.lock(); self.imageErrors.append(String(describing: error)); self.imageLock.unlock()
            }
        }
    }

    private static func writeImage(_ bytes: Data, width: Int, height: Int, rowBytes: Int, to url: URL) throws {
        guard let provider = CGDataProvider(data: bytes as CFData),
              let image = CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
                                  bytesPerRow: rowBytes, space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedFirst.rawValue)
                                    .union(.byteOrder32Little),
                                  provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent),
              let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
            throw CaptureError.unavailable("Could not create stream evidence PNG")
        }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else { throw CaptureError.unavailable("Could not write stream evidence PNG") }
    }

    private func stopStream() async throws {
        if let stream {
            try await stream.stopCapture()
            self.stream = nil
        }
        callbackQueue.sync { stopped = true }
    }

    func finish() async throws {
        do { try await stopStream() }
        catch { callbackQueue.sync { errors.append("SCStream cleanup: \(error)"); stopped = true } }
        imageQueue.sync {}
        try callbackQueue.sync {
            imageLock.lock()
            let imageFailures = imageErrors, saved = writtenImages
            imageLock.unlock()
            let failures = errors + imageFailures
            var data = Data()
            for record in records {
                data.append(try JSONSerialization.data(withJSONObject: record, options: .sortedKeys)); data.append(10)
            }
            try data.write(to: directory.appendingPathComponent("frames.jsonl"), options: .atomic)
            var timebase = mach_timebase_info_data_t()
            guard mach_timebase_info(&timebase) == KERN_SUCCESS else {
                throw CaptureError.unavailable("Could not read the diagnostic Mach clock scale")
            }
            var summary: [String: Any] = ["complete": true, "error": failures.isEmpty ? NSNull() : failures as Any,
                "pid": pid, "window": NSNull(), "record_count": records.count,
                "image_count": saved, "reserved_images": imageCount, "skipped_images": skippedImages,
                "dropped_records": droppedRecords, "truncated": droppedRecords > 0 || imageCount == StreamEvidenceLimits.images,
                "limits": ["seconds": StreamEvidenceLimits.seconds, "records": StreamEvidenceLimits.records,
                           "images": StreamEvidenceLimits.images, "pending_images": 2] as [String: Any],
                "window_rectangle": [windowRectangle.minX, windowRectangle.minY, windowRectangle.width, windowRectangle.height],
                "snapshot_comparator_unchanged": true, "captures_audio": false, "captures_microphone": false,
                "scope": "initial-fixed-window-geometry", "geometry_change": NSNull()]
            summary["mach_timebase"] = ["numerator": timebase.numer, "denominator": timebase.denom]
            if let windowID { summary["window"] = windowID }
            if let geometryChange { summary["geometry_change"] = geometryChange }
            try JSONSerialization.data(withJSONObject: summary, options: [.prettyPrinted, .sortedKeys])
                .write(to: directory.appendingPathComponent("summary.json"), options: .atomic)
            if !failures.isEmpty { throw CaptureError.unavailable(failures.joined(separator: "; ")) }
        }
    }

    // Exercise real pixel buffers, metadata and PNG ownership without opening a
    // stream or asking for permission. The Python fixture also verifies files.
    static func selfTest(directory: URL) async throws {
        func require(_ condition: Bool, _ message: String) throws {
            if !condition { throw CaptureError.unavailable("Stream fixture: \(message)") }
        }
        try require(StreamEvidenceLimits.permits(elapsed: 89.99, count: 5999), "early bound")
        try require(!StreamEvidenceLimits.permits(elapsed: 90, count: 0), "time bound")
        try require(!StreamEvidenceLimits.permits(elapsed: 0, count: 6000), "record bound")
        let recorder = try StreamDiagnostic(directory: directory, pid: 12345)
        recorder.windowID = 37
        recorder.windowRectangle = CGRect(x: 100, y: 200, width: 64, height: 64)
        recorder.panelRectangle = CGRect(x: 100, y: 210, width: 64, height: 54)
        recorder.startedHost = hostSeconds()
        var rawPixels: CVPixelBuffer?
        try require(CVPixelBufferCreate(kCFAllocatorDefault, 128, 128, kCVPixelFormatType_32BGRA,
                                       nil, &rawPixels) == kCVReturnSuccess, "pixel allocation")
        guard let pixels = rawPixels else { throw CaptureError.unavailable("Missing fixture pixels") }
        CVPixelBufferLockBaseAddress(pixels, [])
        guard let bytes = CVPixelBufferGetBaseAddress(pixels) else { throw CaptureError.unavailable("Missing fixture bytes") }
        let rowBytes = CVPixelBufferGetBytesPerRow(pixels)
        memset(bytes, 0, rowBytes * 128)
        let nonce = 0x8127
        for index in 0..<20 {
            let white = index < 4 ? index % 2 == 0 : nonce & (1 << (index - 4)) != 0
            for y in (10 + 8 + index / 4 * 3) * 2..<(10 + 11 + index / 4 * 3) * 2 {
                for x in (8 + index % 4 * 3) * 2..<(11 + index % 4 * 3) * 2 {
                    let pixel = bytes.advanced(by: y * rowBytes + x * 4).assumingMemoryBound(to: UInt8.self)
                    pixel[0] = white ? 255 : 0; pixel[1] = pixel[0]; pixel[2] = pixel[0]; pixel[3] = 255
                }
            }
        }
        try require(streamNonce(bytes: bytes, width: 128, height: 128, rowBytes: rowBytes,
                                window: recorder.windowRectangle, panel: recorder.panelRectangle!) == nonce,
                    "scaled/title-bar nonce")
        try require(streamNonce(bytes: bytes, width: 128, height: 128, rowBytes: rowBytes,
                                window: recorder.windowRectangle, panel: CGRect(x: 0, y: 0, width: 64, height: 54)) == nil,
                    "out-of-window rectangle rejection")
        CVPixelBufferUnlockBaseAddress(pixels, [])
        var description: CMVideoFormatDescription?
        try require(CMVideoFormatDescriptionCreateForImageBuffer(allocator: kCFAllocatorDefault,
                    imageBuffer: pixels, formatDescriptionOut: &description) == noErr, "format description")
        guard let description else { throw CaptureError.unavailable("Missing fixture format") }
        var timing = CMSampleTimingInfo(duration: CMTime(value: 1, timescale: 30),
                                       presentationTimeStamp: CMTime(value: 123, timescale: 1), decodeTimeStamp: .invalid)
        var rawSample: CMSampleBuffer?
        try require(CMSampleBufferCreateReadyWithImageBuffer(allocator: kCFAllocatorDefault, imageBuffer: pixels,
                    formatDescription: description, sampleTiming: &timing, sampleBufferOut: &rawSample) == noErr,
                    "sample creation")
        guard let sample = rawSample,
              let array = CMSampleBufferGetSampleAttachmentsArray(sample, createIfNecessary: true) else {
            throw CaptureError.unavailable("Missing fixture sample attachments")
        }
        let attachments = unsafeBitCast(CFArrayGetValueAtIndex(array, 0), to: CFMutableDictionary.self)
        let key = SCStreamFrameInfo.status.rawValue as CFString
        let complete = NSNumber(value: SCFrameStatus.complete.rawValue)
        CFDictionarySetValue(attachments, Unmanaged.passUnretained(key).toOpaque(), Unmanaged.passUnretained(complete).toOpaque())
        recorder.callbackQueue.sync { recorder.receive(sample) }
        // Mutating the IOSurface after delivery must not change retained evidence.
        CVPixelBufferLockBaseAddress(pixels, [])
        memset(bytes, 0, rowBytes * 128)
        CVPixelBufferUnlockBaseAddress(pixels, [])
        let idle = NSNumber(value: SCFrameStatus.idle.rawValue)
        CFDictionarySetValue(attachments, Unmanaged.passUnretained(key).toOpaque(), Unmanaged.passUnretained(idle).toOpaque())
        recorder.callbackQueue.sync { recorder.receive(sample) }
        try await recorder.finish()
        try require(recorder.records.count == 2 && recorder.records[0]["nonce"] as? Int == nonce, "complete frame evidence")
        try require(recorder.records[1]["nonce"] == nil && recorder.imageCount == 1, "idle does not invent pixels")
        let source = CGImageSourceCreateWithURL(directory.appendingPathComponent("stream-0000.png") as CFURL, nil)
        guard let source, let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
              let context = CGContext(data: nil, width: 128, height: 128, bitsPerComponent: 8, bytesPerRow: 512,
                                      space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue),
              let decoded = context.data else { throw CaptureError.unavailable("Stream fixture: PNG decoding") }
        context.draw(image, in: CGRect(x: 0, y: 0, width: 128, height: 128))
        let rgba = decoded.assumingMemoryBound(to: UInt8.self)
        let whitePixels = (0..<(128 * 128)).filter { rgba[$0 * 4] == 255 && rgba[$0 * 4 + 1] == 255 && rgba[$0 * 4 + 2] == 255 }.count
        try require(whitePixels == (nonce.nonzeroBitCount + 2) * 36, "retained PNG owns pixels after IOSurface mutation")
        do {
            _ = try StreamDiagnostic(directory: directory, pid: 12345)
            throw CaptureError.unavailable("Stream fixture: accepted stale output")
        } catch CaptureError.unavailable(let message) {
            try require(message == "Stream diagnostic directory must be empty", "stale evidence rejection")
        }
    }
}
