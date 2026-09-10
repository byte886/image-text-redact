import Vision
import AppKit
import Foundation

let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: path),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot load image\n".data(using: .utf8)!)
    exit(1)
}
let W = CGFloat(cg.width), H = CGFloat(cg.height)
let req = VNRecognizeTextRequest { req, err in
    guard let obs = req.results as? [VNRecognizedTextObservation] else { return }
    for o in obs {
        guard let cand = o.topCandidates(1).first else { continue }
        let b = o.boundingBox // normalized, origin bottom-left
        let px = b.origin.x * W
        let pyTop = (1.0 - b.origin.y - b.size.height) * H
        let pw = b.size.width * W
        let ph = b.size.height * H
        // 用 \t 分隔：文本, x, yTop, w, h
        print("\(cand.string)\t\(Int(px))\t\(Int(pyTop))\t\(Int(pw))\t\(Int(ph))")
    }
}
req.recognitionLanguages = ["zh-Hans", "en-US"]
req.recognitionLevel = .accurate
req.usesLanguageCorrection = false
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try handler.perform([req])
