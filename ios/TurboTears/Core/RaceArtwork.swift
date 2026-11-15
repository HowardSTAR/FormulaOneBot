import Foundation

struct RaceArtworkCatalog: Sendable {
    struct Countries: Decodable, Sendable {
        let aliases: [String: String]
        let events: [String: String]
    }
    let countries: Countries

    init(countriesData: Data) throws {
        countries = try JSONDecoder().decode(Countries.self, from: countriesData)
    }

    func flag(country: String?, eventName: String) -> String? {
        if let country, !country.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return countries.aliases[Self.normalize(country)]
        }
        let name = Self.normalize(eventName).replacingOccurrences(of: #" grand prix$"#, with: "", options: .regularExpression)
        return countries.events[name]
    }

    func routeName(eventName: String, location: String?, season: Int) -> String {
        let special = season == 2026 && eventName.localizedCaseInsensitiveContains("bahrain")
            && ["sepang", "kuala lumpur", "malaysia"].contains { (location ?? "").localizedCaseInsensitiveContains($0) }
        return special ? "Sepang Grand Prix" : eventName
    }

    private static func normalize(_ value: String) -> String {
        value.folding(options: .diacriticInsensitive, locale: Locale(identifier: "en_US_POSIX"))
            .lowercased().replacingOccurrences(of: ".", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
    }
}
