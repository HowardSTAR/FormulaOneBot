import SwiftUI
import CryptoKit

struct WeekendScreen: View {
    @State private var store: WeekendStore
    @State private var season = Calendar.current.component(.year, from: Date())
    @State private var round = 0
    @State private var showSettings = false
    @State private var showCircuit = false
    private let api: WeekendAPI
    @Binding var address: String

    init(baseURL: URL, address: Binding<String>) {
        let serverKey = SHA256.hash(data: Data(baseURL.absoluteString.utf8))
            .map { String(format: "%02x", $0) }.joined()
        let cache = WeekendCache(directory: URL.cachesDirectory
            .appending(path: "TurboTears/Weekends/\(serverKey)"))
        _store = State(initialValue: WeekendStore(api: WeekendAPI(baseURL: baseURL), cache: cache))
        self.api = WeekendAPI(baseURL: baseURL)
        _address = address
    }

    private var selection: WeekendSelection {
        WeekendSelection(season: season, round: round == 0 ? nil : round)
    }

    var body: some View {
        NavigationStack {
          TimelineView(.periodic(from: .now, by: 30)) { timeline in
            List {
                if store.isCached {
                    Section {
                        Label("Сохранённая копия", systemImage: "internaldrive")
                        if let date = store.savedAt {
                            Text("Сохранено: \(date.formatted(date: .abbreviated, time: .shortened))")
                                .font(.footnote).foregroundStyle(TurboTheme.muted)
                        }
                    }
                }
                if let message = store.message {
                    Section {
                        Label(message, systemImage: "exclamationmark.triangle")
                        retryButton
                    }
                }
                if let weekend = store.weekend {
                    content(weekend, now: timeline.date)
                } else if store.isLoading {
                    Section { ProgressView("Загружаем уик-энд…") }
                } else if store.message == nil {
                    ContentUnavailableView("Уик-энд", systemImage: "flag.checkered",
                                           description: Text("Потяните вниз, чтобы загрузить расписание."))
                }
            }
            .scrollContentBackground(.hidden)
            .background(TurboTheme.background)
            .foregroundStyle(TurboTheme.ink)
            .tint(TurboTheme.accent)
            .navigationTitle("Уик-энд")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Menu {
                        Picker("Сезон", selection: $season) {
                            ForEach((1950...max(2027, Calendar.current.component(.year, from: Date()) + 1)).reversed(), id: \.self) {
                                Text(String($0)).tag($0)
                            }
                        }
                        Picker("Этап", selection: $round) {
                            Text("Ближайший").tag(0)
                            ForEach(1...30, id: \.self) { Text("Этап \($0)").tag($0) }
                        }
                    } label: { Label(String(season), systemImage: "calendar") }
                    .accessibilityLabel("Выбрать сезон и этап. Сезон \(season)")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Настройки", systemImage: "gearshape") { showSettings = true }
                }
            }
            .refreshable { await store.load(selection) }
            .task(id: selection) { await store.load(selection) }
            .sheet(isPresented: $showSettings) { ServerSettings(address: $address) }
            .sheet(isPresented: $showCircuit) {
                if let weekend = store.weekend { CircuitProfileSheet(api: api, weekend: weekend) }
            }
          }
        }
    }

    private var retryButton: some View {
        Button("Повторить загрузку", systemImage: "arrow.clockwise") {
            Task { await store.load(selection) }
        }
        .disabled(store.isLoading)
        .frame(minHeight: 44)
    }

    @ViewBuilder private func content(_ weekend: Weekend, now: Date) -> some View {
        if let event = weekend.event {
            Section {
                VStack(alignment: .leading, spacing: 12) {
                    Label("Этап \(event.round) · \(String(weekend.season))", systemImage: "flag.checkered")
                        .font(.subheadline.weight(.semibold))
                    Text(event.name).font(.largeTitle.bold()).fixedSize(horizontal: false, vertical: true)
                    Text([event.location, event.country].compactMap { $0 }.joined(separator: " · "))
                        .foregroundStyle(TurboTheme.muted)
                    Text("Старт гонки").font(.subheadline).foregroundStyle(TurboTheme.muted)
                    if event.isCancelled {
                        Label("Этап отменён", systemImage: "calendar.badge.minus").font(.headline)
                    } else if let date = weekend.raceStart {
                        Text(date, format: .dateTime.day().month(.wide).hour().minute())
                            .font(.title3.weight(.semibold)).monospacedDigit()
                    } else {
                        if let date = event.date { Text("Дата этапа: \(date)") }
                        Text("Время старта уточняется").foregroundStyle(TurboTheme.muted)
                    }
                }.padding(.vertical, 12).accessibilityElement(children: .combine)
                    .listRowBackground(TurboTheme.surface)
            }
            Section {
                Button("Статистика трассы", systemImage: "point.topleft.down.to.point.bottomright.curvepath") { showCircuit = true }
                    .frame(minHeight: 44)
            }.listRowBackground(TurboTheme.surface)
            Section {
                if event.isCancelled {
                    Label("Сессии не состоятся", systemImage: "calendar.badge.minus")
                } else if weekend.sessions.isEmpty {
                    Text("Расписание пока недоступно. Попробуйте загрузить его позже.")
                    retryButton
                } else {
                        ForEach(Array(weekend.orderedSessions.enumerated()), id: \.offset) { index, session in
                            let next = weekend.nextSessionIndex(at: now) == index
                            Group {
                                if session.canOpenResults(at: now) {
                                    NavigationLink {
                                        SessionResultsScreen(api: api, weekend: weekend, selected: session.code)
                                    } label: { sessionRow(session, next: next, results: true) }
                                } else {
                                    sessionRow(session, next: next, results: false)
                                }
                            }
                            .padding(10)
                            .background(next ? TurboTheme.tint : .clear, in: RoundedRectangle(cornerRadius: 12))
                        }
                    .listRowBackground(TurboTheme.surface)

                }
            } header: {
                Text("Расписание сессий")
                if !event.isCancelled, let url = calendarURL(weekend) {
                    Link("В календарь", destination: url).font(.subheadline)
                }
            } footer: {
                Text("Время на устройстве: \(TimeZone.current.identifier). Данные могут обновляться с задержкой.")
            }
        } else {
            Section {
                ContentUnavailableView(
                    weekend.status == "season_finished" ? "Сезон завершён" : "Расписание недоступно",
                    systemImage: "calendar",
                    description: Text(weekend.status == "season_finished"
                        ? "Выберите другой сезон или конкретный этап в меню сверху."
                        : "Провайдер пока не вернул расписание. Попробуйте ещё раз позже.")
                )
                retryButton
            }
        }
    }
    private func sessionRow(_ session: WeekendSession, next: Bool, results: Bool) -> some View {
        HStack(alignment: .center, spacing: 14) {
            if let date = session.startsAt {
                VStack(spacing: 2) {
                    Text(date, format: .dateTime.day()).font(.title2.weight(.semibold))
                    Text(date, format: .dateTime.weekday(.abbreviated).month(.abbreviated))
                        .font(.caption).foregroundStyle(TurboTheme.muted)
                }.frame(minWidth: 52)
            }
            VStack(alignment: .leading, spacing: 5) {
                Text(session.title).font(.headline)
                if let date = session.startsAt {
                    Text(date, format: .dateTime.hour().minute()).monospacedDigit().foregroundStyle(TurboTheme.muted)
                } else { Text("Время уточняется").foregroundStyle(TurboTheme.muted) }
                if next { Text("Следующая сессия").font(.footnote).foregroundStyle(TurboTheme.accent) }
                if results { Text("Результаты").font(.footnote).foregroundStyle(TurboTheme.muted) }
            }
            Spacer(minLength: 0)
        }.padding(.vertical, 4).accessibilityElement(children: .combine)
    }

    private func calendarURL(_ weekend: Weekend) -> URL? {
        guard let event = weekend.event else { return nil }
        var components = URLComponents(url: api.baseURL.appending(path: "api/calendar/weekend.ics"), resolvingAgainstBaseURL: false)
        components?.queryItems = [.init(name: "season", value: String(weekend.season)), .init(name: "round", value: String(event.round))]
        return components?.url
    }

}

struct ServerSettings: View {
    @Binding var address: String
    @State private var draft = ""
    @Environment(\.dismiss) private var dismiss

    private var valid: Bool {
        guard let url = URL(string: draft.trimmingCharacters(in: .whitespacesAndNewlines)),
              let host = url.host, !host.isEmpty, url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil else { return false }
        return url.scheme == "https" || (url.scheme == "http" && ["localhost", "127.0.0.1", "::1"].contains(host))
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Сервер API") {
                    TextField("https://example.com", text: $draft)
                        .textContentType(.URL).keyboardType(.URL)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                    Text("Для разработки в симуляторе: http://localhost:8000. Для удалённого сервера нужен HTTPS.")
                        .font(.footnote).foregroundStyle(TurboTheme.muted)
                }
            }
            .navigationTitle("Настройки")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Отмена") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Сохранить") {
                        address = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                        dismiss()
                    }.disabled(!valid)
                }
            }
            .onAppear { draft = address }
        }
    }
}
