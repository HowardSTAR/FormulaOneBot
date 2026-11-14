import Foundation

extension Weekend {
    var orderedSessions: [WeekendSession] {
        sessions.enumerated().sorted {
            let lhs = $0.element.startsAt ?? .distantFuture
            let rhs = $1.element.startsAt ?? .distantFuture
            return lhs == rhs ? $0.offset < $1.offset : lhs < rhs
        }.map(\.element)
    }
    var raceStart: Date? { sessions.first { $0.code == "race" }?.startsAt ?? event?.startsAt }
    func nextSessionIndex(at now: Date) -> Int? {
        orderedSessions.firstIndex { ($0.startsAt ?? .distantPast) > now }
    }
}

extension WeekendSession {
    var resultsPath: String? {
        switch code {
        case "practice_1", "practice_2", "practice_3": "api/practice-results"
        case "qualifying": "api/quali-results"
        case "sprint_qualifying": "api/sprint-quali-results"
        case "sprint": "api/sprint-results"
        case "race": "api/race-results"
        default: nil
        }
    }
    var practice: Int? {
        switch code { case "practice_1": 1; case "practice_2": 2; case "practice_3": 3; default: nil }
    }
    func canOpenResults(at now: Date) -> Bool {
        resultsPath != nil && startsAt.map { $0 <= now } == true
    }
}

struct SessionClassification: Decodable, Sendable {
    let season: Int?
    let round: Int?
    let session: Int?
    let results: [ClassificationRow]?

    func matchingRows(season: Int, round: Int, practice: Int?) -> [ClassificationRow] {
        guard self.season == season, self.round == round,
              practice == nil || session == practice else { return [] }
        let rows = results ?? []
        return rows.sorted {
            if practice != nil {
                let lhs = Self.lapSeconds($0.best) ?? .infinity
                let rhs = Self.lapSeconds($1.best) ?? .infinity
                if lhs != rhs { return lhs < rhs }
            }
            let lhs = ($0.position ?? 0) > 0 ? $0.position! : Int.max
            let rhs = ($1.position ?? 0) > 0 ? $1.position! : Int.max
            return lhs < rhs
        }
    }

    static func lapSeconds(_ value: String?) -> Double? {
        guard let raw = value else { return nil }
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard value.range(of: #"^(?:[0-9]+:)?[0-9]{1,2}\.[0-9]{3}$"#, options: .regularExpression) != nil else { return nil }
        let parts = value.split(separator: ":")
        guard parts.count <= 2, let seconds = Double(parts.last ?? "") else { return nil }
        let result = seconds + (parts.count == 2 ? (Double(parts[0]) ?? 0) * 60 : 0)
        return result > 0 ? result : nil
    }
}

struct ClassificationRow: Decodable, Sendable {
    let position: Int?
    let name: String?
    let driver: String?
    let code: String?
    let team: String?
    let best: String?
    let time: String?
    let gap: String?
    let status: String?
    let laps: Int?
    let points: Double?
    let segment: String?
    var displayName: String { name ?? driver ?? code ?? "Пилот" }
}

extension WeekendAPI {
    func classification(season: Int, round: Int, session selected: WeekendSession) async throws -> [ClassificationRow] {
        guard let path = selected.resultsPath else { return [] }
        var query = [URLQueryItem(name: "season", value: String(season)), URLQueryItem(name: "round", value: String(round))]
        if let practice = selected.practice { query.append(.init(name: "session", value: String(practice))) }
        let response: SessionClassification = try await data(path: path, query: query)
        return response.matchingRows(season: season, round: round, practice: selected.practice)
    }
}
