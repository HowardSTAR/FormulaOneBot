import Foundation

struct Weekend: Codable, Sendable {
    let status: String
    let season: Int
    let event: WeekendEvent?
    let sessions: [WeekendSession]
    let scheduleStatus: String

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            for options: ISO8601DateFormatter.Options in [
                [.withInternetDateTime, .withFractionalSeconds], [.withInternetDateTime]
            ] {
                let formatter = ISO8601DateFormatter()
                formatter.formatOptions = options
                if let date = formatter.date(from: value) { return date }
            }
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath,
                                                    debugDescription: "Invalid ISO 8601 instant"))
        }
        return decoder
    }
}

struct WeekendEvent: Codable, Sendable, Identifiable {
    let id: String
    let round: Int
    let name: String
    let country: String?
    let location: String?
    // A calendar day is deliberately kept separate from an instant.
    let date: String?
    let startsAt: Date?
    let isCancelled: Bool
}

struct WeekendSession: Codable, Sendable {
    // Strings preserve forward compatibility with future server enum values.
    let code: String
    let sourceName: String
    let startsAt: Date?

    var title: String {
        switch code {
        case "practice_1": "Практика 1"
        case "practice_2": "Практика 2"
        case "practice_3": "Практика 3"
        case "qualifying": "Квалификация"
        case "sprint": "Спринт"
        case "sprint_qualifying": "Спринт-квалификация"
        case "race": "Гонка"
        default: sourceName
        }
    }
}

struct WeekendSelection: Hashable, Sendable {
    let season: Int
    var round: Int? = nil

    var cacheKey: String { "\(season)-\(round.map(String.init) ?? "next")" }
}
