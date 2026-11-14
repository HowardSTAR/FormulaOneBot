import Foundation
import Testing
@testable import TurboTearsCore

private let payload = Data("""
{"status":"ok","season":2026,"event":{"id":"2026:1","round":1,"name":"Test GP",
"country":null,"location":null,"date":"2026-03-08","starts_at":"2026-03-08T04:00:00.123Z","is_cancelled":false},
"sessions":[{"code":"future_code","source_name":"Future Session","starts_at":null}],"schedule_status":"available","extra":true}
""".utf8)

@Test func decodesContractAndPreservesUnknownSessions() throws {
    let result = try Weekend.decoder().decode(Weekend.self, from: payload)
    #expect(result.event?.date == "2026-03-08")
    #expect(result.event?.startsAt != nil)
    #expect(result.sessions[0].title == "Future Session")
    #expect(result.sessions[0].startsAt == nil)
    let wholeSeconds = Data(String(decoding: payload, as: UTF8.self).replacingOccurrences(of: ".123Z", with: "Z").utf8)
    #expect(try Weekend.decoder().decode(Weekend.self, from: wholeSeconds).event?.startsAt != nil)
}

@Test func buildsSelectedAndNextWeekendRequests() throws {
    let api = WeekendAPI(baseURL: URL(string: "https://example.test")!)
    #expect(try api.request(for: .init(season: 2026)).url?.absoluteString == "https://example.test/api/v1/weekend?season=2026")
    #expect(try api.request(for: .init(season: 2026, round: 2)).url?.absoluteString == "https://example.test/api/v1/weekend?season=2026&round=2")
}

private struct FailingAPI: WeekendLoading {
    func fetch(_ selection: WeekendSelection) async throws -> Weekend { throw URLError(.notConnectedToInternet) }
}

private struct EmptyAPI: WeekendLoading {
    func fetch(_ selection: WeekendSelection) async throws -> Weekend {
        Weekend(status: "no_schedule", season: selection.season, event: nil, sessions: [], scheduleStatus: "not_applicable")
    }
}

@Test @MainActor func offlineCacheIsIsolatedBySelection() async throws {
    let directory = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let cache = WeekendCache(directory: directory)
    let selection = WeekendSelection(season: 2026)
    let result = try Weekend.decoder().decode(Weekend.self, from: payload)
    _ = try await cache.write(result, for: selection)
    let store = WeekendStore(api: FailingAPI(), cache: cache)
    await store.load(selection)
    #expect(store.weekend?.event?.id == "2026:1")
    #expect(store.isCached)
    #expect(store.message != nil)
    #expect(!store.isLoading)
    await store.load(.init(season: 2025))
    #expect(store.weekend == nil)
    #expect(!store.isCached)
}

@Test @MainActor func upstreamEmptyDataDoesNotEraseCachedWeekend() async throws {
    let directory = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let cache = WeekendCache(directory: directory)
    let selection = WeekendSelection(season: 2026)
    _ = try await cache.write(Weekend.decoder().decode(Weekend.self, from: payload), for: selection)
    let store = WeekendStore(api: EmptyAPI(), cache: cache)
    await store.load(selection)
    #expect(store.weekend?.event?.id == "2026:1")
    #expect(store.isCached)
    #expect(store.message != nil)
}

private final class StubURLProtocol: URLProtocol, @unchecked Sendable {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let status = request.url?.host == "missing.test" ? 404 : 200
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status,
                             httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: payload)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Test func networkDecodingAndNotFound() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [StubURLProtocol.self]
    let session = URLSession(configuration: configuration)
    defer { session.invalidateAndCancel() }
    let api = WeekendAPI(baseURL: URL(string: "https://example.test")!, session: session)
    #expect(try await api.fetch(.init(season: 2026)).event?.id == "2026:1")
    let missing = WeekendAPI(baseURL: URL(string: "https://missing.test")!, session: session)
    do {
        _ = try await missing.fetch(.init(season: 2026))
        Issue.record("Expected 404 error")
    } catch WeekendAPIError.notFound { }
}

@Test func weekendRulesMatchWeb() throws {
    let past = Date(timeIntervalSince1970: 100)
    let future = Date(timeIntervalSince1970: 300)
    let sessions = [WeekendSession(code: "race", sourceName: "Race", startsAt: future),
                    WeekendSession(code: "practice_1", sourceName: "Practice 1", startsAt: past),
                    WeekendSession(code: "unknown", sourceName: "Unknown", startsAt: nil)]
    let weekend = Weekend(status: "ok", season: 2026, event: nil, sessions: sessions, scheduleStatus: "available")
    #expect(weekend.orderedSessions.map(\.code) == ["practice_1", "race", "unknown"])
    #expect(weekend.nextSessionIndex(at: Date(timeIntervalSince1970: 200)) == 1)
    #expect(weekend.raceStart == future)
    #expect(sessions[1].canOpenResults(at: past))
    #expect(!sessions[0].canOpenResults(at: past))
    #expect(!sessions[2].canOpenResults(at: future))
}

@Test func refusesOtherEventAndOtherPracticeResults() throws {
    let json = Data("""
    {"season":2026,"round":1,"session":1,"results":[
    {"position":1,"name":"Slow","best":"1:22.000"},
    {"position":2,"name":"Fast","best":"1:21.000"}]}
    """.utf8)
    let result = try JSONDecoder().decode(SessionClassification.self, from: json)
    #expect(result.matchingRows(season: 2025, round: 1, practice: 1).isEmpty)
    #expect(result.matchingRows(season: 2026, round: 2, practice: 1).isEmpty)
    #expect(result.matchingRows(season: 2026, round: 1, practice: 2).isEmpty)
    #expect(result.matchingRows(season: 2026, round: 1, practice: 1).first?.name == "Fast")
    #expect(result.matchingRows(season: 2026, round: 1, practice: nil).first?.name == "Slow")
}

@Test func refusesCircuitProfileFromDifferentEvent() throws {
    let json = Data("""
    {"status":"stale","season":2026,"round":1,"profile":{
    "name":"Test Circuit","season":2026,"round":1,"eventName":"Other GP",
    "compounds":[],"ratings":[],"sources":[]}}
    """.utf8)
    let response = try JSONDecoder().decode(CircuitProfileResponse.self, from: json)
    let weekend = try Weekend.decoder().decode(Weekend.self, from: payload)
    #expect(response.matching(weekend) == nil)
}

@Test func lapParserRejectsUnpublishedAndInvalidTimes() {
    #expect(SessionClassification.lapSeconds("1:21.123") == 81.123)
    #expect(SessionClassification.lapSeconds(" 59.123 ") == 59.123)
    #expect(SessionClassification.lapSeconds("nan") == nil)
    #expect(SessionClassification.lapSeconds("0.000") == nil)
    #expect(SessionClassification.lapSeconds("DNF") == nil)
}
