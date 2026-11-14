import Foundation

struct CachedWeekend: Codable, Sendable {
    let savedAt: Date
    let weekend: Weekend
}

actor WeekendCache {
    let directory: URL

    init(directory: URL = URL.cachesDirectory.appending(path: "TurboTears/Weekends")) {
        self.directory = directory
    }

    func read(_ selection: WeekendSelection) -> CachedWeekend? {
        guard let data = try? Data(contentsOf: file(for: selection)) else { return nil }
        return try? JSONDecoder().decode(CachedWeekend.self, from: data)
    }

    func write(_ weekend: Weekend, for selection: WeekendSelection) throws -> CachedWeekend {
        let cached = CachedWeekend(savedAt: Date(), weekend: weekend)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONEncoder().encode(cached).write(to: file(for: selection), options: .atomic)
        return cached
    }

    private func file(for selection: WeekendSelection) -> URL {
        directory.appending(path: "\(selection.cacheKey).json")
    }
}
