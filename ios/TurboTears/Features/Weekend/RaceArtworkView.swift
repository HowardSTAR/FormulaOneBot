import SwiftUI
import WebKit

private enum Artwork {
    static let catalog: RaceArtworkCatalog? = {
        guard let url = Bundle.main.url(forResource: "race-countries", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? RaceArtworkCatalog(countriesData: data)
    }()
}

struct RaceFlagBackground: View {
    let event: WeekendEvent
    let baseURL: URL
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        if !reduceTransparency, contrast != .increased,
           let code = Artwork.catalog?.flag(country: event.country, eventName: event.name) {
            GeometryReader { geometry in
                RemoteSVG(url: baseURL.appending(path: "flags").appending(component: "\(code).svg"), contour: false)
                    .frame(width: geometry.size.width, height: geometry.size.height)
            }
                .opacity(scheme == .dark ? 0.10 : 0.06)
                .mask {
                    LinearGradient(stops: [.init(color: .clear, location: 0), .init(color: .black, location: 0.14),
                        .init(color: .black, location: 0.86), .init(color: .clear, location: 1)], startPoint: .leading, endPoint: .trailing)
                        .mask {
                            LinearGradient(stops: [.init(color: .clear, location: 0), .init(color: .black, location: 0.22),
                                .init(color: .black, location: 0.78), .init(color: .clear, location: 1)], startPoint: .top, endPoint: .bottom)
                        }
                }
                .accessibilityHidden(true).allowsHitTesting(false)
        }
    }
}

struct RaceCircuitMap: View {
    let event: WeekendEvent
    let season: Int
    let baseURL: URL
    var body: some View {
        let name = Artwork.catalog?.routeName(eventName: event.name, location: event.location, season: season) ?? event.name
        RemoteSVG(url: baseURL.appending(path: "static/circuit").appending(component: name + ".svg"), contour: true)
            .accessibilityHidden(true)
    }
}

private actor SVGCache {
    static let shared = SVGCache()
    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.urlCache = URLCache(memoryCapacity: 8_000_000, diskCapacity: 64_000_000, diskPath: "TurboTearsSVG")
        return URLSession(configuration: config)
    }()
    func load(_ url: URL) async throws -> Data {
        var request = URLRequest(url: url)
        request.timeoutInterval = 20
        do {
            let (data, response) = try await session.data(for: request)
            guard let response = response as? HTTPURLResponse, response.statusCode == 200,
                  data.count < 2_000_000, String(decoding: data, as: UTF8.self).contains("<svg") else {
                throw WeekendAPIError.invalidResponse
            }
            return data
        } catch {
            try Task.checkCancellation()
            if let cached = session.configuration.urlCache?.cachedResponse(for: request),
               (cached.response as? HTTPURLResponse)?.statusCode == 200,
               String(decoding: cached.data, as: UTF8.self).contains("<svg") { return cached.data }
            throw error
        }
    }
}

private struct RemoteSVG: View {
    let url: URL
    let contour: Bool
    @State private var data: Data?
    @State private var failed = false
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Group {
            if let data {
                SVGImage(data: data, contour: contour, dark: scheme == .dark)
            } else if contour {
                Text(failed ? "Схема временно недоступна" : "Загружаем схему…")
                    .font(.caption).foregroundStyle(TurboTheme.muted)
            } else { Color.clear }
        }
        .task(id: url) {
            data = nil; failed = false
            do {
                let loaded = try await SVGCache.shared.load(url)
                try Task.checkCancellation()
                data = loaded
            } catch { if !Task.isCancelled { failed = true } }
        }
    }
}

/// An inert SVG image surface, not a web screen. No JavaScript, navigation or external subresources.
private struct SVGImage: UIViewRepresentable {
    let data: Data
    let contour: Bool
    let dark: Bool

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = false
        config.websiteDataStore = .nonPersistent()
        let view = WKWebView(frame: .zero, configuration: config)
        view.isOpaque = false
        view.backgroundColor = .clear
        view.scrollView.backgroundColor = .clear
        view.scrollView.isScrollEnabled = false
        view.isUserInteractionEnabled = false
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        let key = "\(data.hashValue):\(dark):\(contour)"
        guard context.coordinator.key != key else { return }
        context.coordinator.key = key
        var svg = data
        if contour {
            let parser = ContourParser()
            let xml = XMLParser(data: data)
            xml.shouldResolveExternalEntities = false
            xml.delegate = parser
            guard xml.parse(), let path = parser.paths.max(by: { $0.count < $1.count }) else { return }
            let color = dark ? "#ff9b92" : "#b92b25"
            svg = Data("<svg xmlns='http://www.w3.org/2000/svg' viewBox='\(parser.viewBox)'><path d='\(path)' fill='none' stroke='\(color)' stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round'/><path d='\(path)' fill='none' stroke='\(dark ? "#141518" : "#f5f5f7")' stroke-width='0.5' stroke-linecap='round' stroke-linejoin='round'/></svg>".utf8)
        }
        let fit = contour ? "contain" : "cover"
        let html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'\"></head><body style='margin:0;background:transparent'><img style='width:100%;height:100%;object-fit:\(fit);display:block' src='data:image/svg+xml;base64,\(svg.base64EncodedString())'></body></html>"
        view.loadHTMLString(html, baseURL: nil)
    }
    func makeCoordinator() -> Coordinator { Coordinator() }
    final class Coordinator { var key = "" }
}

private final class ContourParser: NSObject, XMLParserDelegate {
    var viewBox = "0 0 121 85"
    var paths: [String] = []
    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName: String?, attributes: [String: String]) {
        if elementName == "svg", let value = attributes["viewBox"], value.range(of: #"^[0-9eE., +\-]+$"#, options: .regularExpression) != nil { viewBox = value }
        if elementName == "path", let value = attributes["d"] {
            let pattern = #"[Mm][^Mm]*"#
            if let expression = try? NSRegularExpression(pattern: pattern) {
                paths += expression.matches(in: value, range: NSRange(value.startIndex..., in: value)).compactMap {
                    Range($0.range, in: value).map { String(value[$0]) }
                }.filter { $0.range(of: #"^[0-9a-zA-Z., +\-\s]+$"#, options: .regularExpression) != nil }
            }
        }
    }
}
struct SupporterMark: Shape {
    func path(in rect: CGRect) -> Path {
        let scale = min(rect.width, rect.height) / 32
        let origin = CGPoint(x: rect.midX - 16 * scale, y: rect.midY - 16 * scale)
        func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: origin.x + x * scale, y: origin.y + y * scale) }
        return Path { path in
            for polygon: [(CGFloat, CGFloat)] in [
                [(16,2),(28,9),(28,23),(16,30),(4,23),(4,9)],
                [(16,5),(25,10),(25,22),(16,27),(7,22),(7,10)],
                [(10,11),(16,11),(13,16),(18,16),(10,24),(13,17),(8,17)],
                [(19,11),(24,11),(21,16),(16,16)]
            ] {
                path.move(to: point(polygon[0].0, polygon[0].1))
                for pair in polygon.dropFirst() { path.addLine(to: point(pair.0, pair.1)) }
                path.closeSubpath()
            }
        }
    }
}
