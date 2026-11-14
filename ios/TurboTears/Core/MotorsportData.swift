import Foundation

struct StandingRow: Decodable, Sendable {
    let position: Int
    let name: String
    let points: Double?
    let constructorName: String?
    let code: String?
}

struct StandingsResponse: Decodable, Sendable {
    let season: Int?
    let round: Int?
    let drivers: [StandingRow]?
    let constructors: [StandingRow]?
}

struct CircuitProfileResponse: Decodable, Sendable {
    let status: String
    let season: Int
    let round: Int
    let profile: CircuitProfile?

    func matching(_ weekend: Weekend) -> CircuitProfile? {
        guard ["ok", "stale"].contains(status), season == weekend.season,
              round == weekend.event?.round, let profile,
              profile.season == season, profile.round == round,
              profile.eventName == weekend.event?.name else { return nil }
        return profile
    }
}

struct CircuitProfile: Decodable, Sendable {
    struct Rating: Decodable, Sendable { let label: String; let value: Int }
    struct Winner: Decodable, Sendable { let name: String; let wins: Int }
    struct Source: Decodable, Sendable { let title: String; let href: String }
    struct Record: Decodable, Sendable { let time: String; let driver: String; let year: Int }
    struct Pressures: Decodable, Sendable { let front: String; let rear: String }
    let name: String
    let season: Int
    let round: Int
    let eventName: String
    let stale: Bool?
    let updatedAt: String?
    let compounds: [String]
    let ratings: [Rating]
    let team: Winner?
    let driver: Winner?
    let opened: Int?
    let firstRace: Int?
    let historyThrough: Int?
    let lapRecord: Record?
    let pitLoss: String?
    let pressures: Pressures?
    let sources: [Source]
}

extension WeekendAPI {
    func data<Value: Decodable & Sendable>(path: String, query: [URLQueryItem]) async throws -> Value {
        guard var components = URLComponents(url: baseURL.appending(path: path), resolvingAgainstBaseURL: false) else {
            throw WeekendAPIError.invalidURL
        }
        components.queryItems = query
        guard let url = components.url else { throw WeekendAPIError.invalidURL }
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw WeekendAPIError.invalidResponse }
        guard http.statusCode == 200 else { throw WeekendAPIError.server(http.statusCode) }
        return try JSONDecoder().decode(Value.self, from: data)
    }
}
