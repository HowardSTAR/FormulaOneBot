import Foundation

protocol WeekendLoading: Sendable {
    func fetch(_ selection: WeekendSelection) async throws -> Weekend
}

enum WeekendAPIError: Error, LocalizedError {
    case invalidURL, notFound, server(Int), invalidResponse

    var errorDescription: String? {
        switch self {
        case .invalidURL: "Проверьте адрес сервера в настройках приложения."
        case .notFound: "Этап не найден. Выберите другой сезон или номер этапа."
        case .server: "Сервер временно недоступен. Повторите загрузку."
        case .invalidResponse: "Не удалось прочитать расписание. Повторите загрузку."
        }
    }
}

struct WeekendAPI: WeekendLoading {
    let baseURL: URL
    var session: URLSession = .shared

    func request(for selection: WeekendSelection) throws -> URLRequest {
        guard ["https", "http"].contains(baseURL.scheme), baseURL.host != nil,
              var components = URLComponents(url: baseURL.appending(path: "api/v1/weekend"),
                                             resolvingAgainstBaseURL: false) else {
            throw WeekendAPIError.invalidURL
        }
        components.queryItems = [URLQueryItem(name: "season", value: String(selection.season))]
        if let round = selection.round {
            components.queryItems?.append(URLQueryItem(name: "round", value: String(round)))
        }
        guard let url = components.url else { throw WeekendAPIError.invalidURL }
        var request = URLRequest(url: url)
        request.timeoutInterval = 20
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return request
    }

    func fetch(_ selection: WeekendSelection) async throws -> Weekend {
        let (data, response) = try await session.data(for: request(for: selection))
        guard let response = response as? HTTPURLResponse else { throw WeekendAPIError.invalidResponse }
        switch response.statusCode {
        case 200: break
        case 404: throw WeekendAPIError.notFound
        default: throw WeekendAPIError.server(response.statusCode)
        }
        do { return try Weekend.decoder().decode(Weekend.self, from: data) }
        catch { throw WeekendAPIError.invalidResponse }
    }
}
