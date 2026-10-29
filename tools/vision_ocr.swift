// Apple Vision OCR (built into macOS, free). Usage: vision_ocr <image.png>
// Prints JSON: a list of lines, each with its text, confidence, box and word boxes.
// Boxes are [x0, y0, x1, y1] as fractions of the page width/height, origin at the top-left.
import Foundation
import Vision
import AppKit

let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let img = NSImage(contentsOf: url),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot load image\n".data(using: .utf8)!)
    exit(1)
}
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = true
req.recognitionLanguages = ["en-US"]
try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])

func box(_ r: CGRect) -> [Double] {
    [Double(r.minX), Double(1 - r.maxY), Double(r.maxX), Double(1 - r.minY)]
}
var lines: [[String: Any]] = []
for obs in req.results ?? [] {
    guard let top = obs.topCandidates(1).first else { continue }
    var words: [[String: Any]] = []
    for w in top.string.split(separator: " ") {
        if let b = try? top.boundingBox(for: w.startIndex..<w.endIndex) {
            words.append(["text": String(w), "box": box(b.boundingBox)])
        }
    }
    lines.append(["text": top.string, "conf": Double(top.confidence), "box": box(obs.boundingBox), "words": words])
}
let data = try JSONSerialization.data(withJSONObject: lines)
FileHandle.standardOutput.write(data)
