// Test-only persistent capture of the explicitly identified game's window.
import CoreGraphics
import Darwin
import Foundation
import ImageIO
import ScreenCaptureKit
import UniformTypeIdentifiers

struct CaptureRequest: Decodable {
    let window: UInt32
    let rectangle: [Int]?
    let path: String
}

enum CaptureError: Error {
    case unavailable(String)
}

@main
struct WindowCapture {
    static func capture(_ request: CaptureRequest, pid: Int32) async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
        guard let window = content.windows.first(where: { $0.windowID == request.window && $0.owningApplication?.processID == pid }) else {
            throw CaptureError.unavailable("The requested window does not belong to the exact game PID")
        }
        let filter = SCContentFilter(desktopIndependentWindow: window)
        let configuration = SCStreamConfiguration()
        configuration.width = Int(window.frame.width.rounded())
        configuration.height = Int(window.frame.height.rounded())
        configuration.showsCursor = false
        configuration.ignoreShadowsSingleWindow = true
        configuration.capturesAudio = false
        configuration.captureMicrophone = false
        var image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: configuration)
        if let values = request.rectangle {
            guard values.count == 4 else { throw CaptureError.unavailable("Expected x,y,width,height") }
            let rectangle = CGRect(x: Double(values[0]), y: Double(values[1]), width: Double(values[2]), height: Double(values[3]))
            guard rectangle.width > 0, rectangle.height > 0, window.frame.contains(rectangle) else {
                throw CaptureError.unavailable("Requested rectangle extends outside the game window")
            }
            let local = rectangle.offsetBy(dx: -window.frame.origin.x, dy: -window.frame.origin.y)
            let scaleX = CGFloat(image.width) / window.frame.width
            let scaleY = CGFloat(image.height) / window.frame.height
            let pixels = CGRect(x: local.origin.x * scaleX, y: local.origin.y * scaleY,
                                width: local.width * scaleX, height: local.height * scaleY)
            guard let cropped = image.cropping(to: pixels),
                  let context = CGContext(data: nil, width: values[2], height: values[3], bitsPerComponent: 8,
                                          bytesPerRow: values[2] * 4, space: CGColorSpaceCreateDeviceRGB(),
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
                throw CaptureError.unavailable("Could not crop the exact game rectangle")
            }
            context.interpolationQuality = .none
            context.draw(cropped, in: CGRect(x: 0, y: 0, width: Double(values[2]), height: Double(values[3])))
            guard let resized = context.makeImage() else { throw CaptureError.unavailable("Could not encode captured game pixels") }
            image = resized
        }
        let url = URL(fileURLWithPath: request.path)
        guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
            throw CaptureError.unavailable("Could not create the requested PNG")
        }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else { throw CaptureError.unavailable("Could not write the requested PNG") }
    }

    static func main() async {
        guard CommandLine.arguments.count == 2, let pid = Int32(CommandLine.arguments[1]), pid > 1,
              CGPreflightScreenCaptureAccess() else {
            fputs("Capture requires the exact game PID and pre-existing permission; no consent requested\n", stderr)
            exit(77)
        }
        print("READY"); fflush(stdout)
        while let line = readLine() {
            do {
                let request = try JSONDecoder().decode(CaptureRequest.self, from: Data(line.utf8))
                try await capture(request, pid: pid)
                print("OK")
            } catch {
                print("ERROR \(error)".replacingOccurrences(of: "\n", with: " "))
            }
            fflush(stdout)
        }
    }
}
