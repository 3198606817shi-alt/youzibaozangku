import AppKit

let arguments = CommandLine.arguments
guard arguments.count == 2 else {
    fputs("Usage: generate_icon.swift <output.png>\n", stderr)
    exit(2)
}

let size = NSSize(width: 1024, height: 1024)
let image = NSImage(size: size)
image.lockFocus()

let background = NSBezierPath(roundedRect: NSRect(x: 42, y: 42, width: 940, height: 940), xRadius: 218, yRadius: 218)
NSColor(calibratedRed: 0.985, green: 0.988, blue: 0.994, alpha: 1).setFill()
background.fill()

let bookmark = NSBezierPath()
bookmark.move(to: NSPoint(x: 286, y: 184))
bookmark.line(to: NSPoint(x: 738, y: 184))
bookmark.curve(to: NSPoint(x: 790, y: 236), controlPoint1: NSPoint(x: 767, y: 184), controlPoint2: NSPoint(x: 790, y: 207))
bookmark.line(to: NSPoint(x: 790, y: 814))
bookmark.line(to: NSPoint(x: 512, y: 654))
bookmark.line(to: NSPoint(x: 234, y: 814))
bookmark.line(to: NSPoint(x: 234, y: 236))
bookmark.curve(to: NSPoint(x: 286, y: 184), controlPoint1: NSPoint(x: 234, y: 207), controlPoint2: NSPoint(x: 257, y: 184))
bookmark.close()
bookmark.lineWidth = 56
bookmark.lineJoinStyle = .round
NSColor(calibratedRed: 1, green: 0.318, blue: 0.286, alpha: 1).setStroke()
bookmark.stroke()

let play = NSBezierPath()
play.move(to: NSPoint(x: 430, y: 354))
play.line(to: NSPoint(x: 664, y: 496))
play.line(to: NSPoint(x: 430, y: 638))
play.close()
NSColor(calibratedRed: 1, green: 0.318, blue: 0.286, alpha: 1).setFill()
play.fill()

image.unlockFocus()
guard let data = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: data),
      let png = bitmap.representation(using: .png, properties: [:]) else {
    fputs("Failed to render PNG\n", stderr)
    exit(1)
}
try png.write(to: URL(fileURLWithPath: arguments[1]))
