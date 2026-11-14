import Foundation
import Observation

@MainActor @Observable
final class WeekendStore {
    private(set) var weekend: Weekend?
    private(set) var isLoading = false
    private(set) var isCached = false
    private(set) var savedAt: Date?
    private(set) var message: String?
    @ObservationIgnored private let api: any WeekendLoading
    @ObservationIgnored private let cache: WeekendCache
    @ObservationIgnored private var generation = UUID()
    @ObservationIgnored private var current: WeekendSelection?

    init(api: any WeekendLoading, cache: WeekendCache = WeekendCache()) {
        self.api = api
        self.cache = cache
    }

    func load(_ selection: WeekendSelection) async {
        let token = UUID()
        generation = token
        if current != selection {
            weekend = nil
            savedAt = nil
            isCached = false
        }
        current = selection
        isLoading = true
        message = nil
        defer { if generation == token { isLoading = false } }
        if weekend == nil, let cached = await cache.read(selection), generation == token {
            weekend = cached.weekend
            savedAt = cached.savedAt
            isCached = true
        }
        do {
            let result = try await api.fetch(selection)
            try Task.checkCancellation()
            guard generation == token else { return }
            // Never replace a useful saved schedule with an upstream empty-data response.
            if result.status == "no_schedule", weekend != nil {
                isCached = true
                message = "Расписание сейчас недоступно. Показана сохранённая копия."
                return
            }
            weekend = result
            isCached = false
            do {
                let entry = try await cache.write(result, for: selection)
                if generation == token { savedAt = entry.savedAt }
            } catch {
                if generation == token { message = "Расписание загружено, но сохранить его для офлайн-доступа не удалось." }
            }
        } catch is CancellationError {
            // A disappearing screen or a new selection cancels its own request.
        } catch {
            guard generation == token, !Task.isCancelled else { return }
            isCached = weekend != nil
            message = (error as? WeekendAPIError)?.errorDescription
                ?? "Нет связи с сервером. Проверьте интернет и повторите загрузку."
        }
    }
}
