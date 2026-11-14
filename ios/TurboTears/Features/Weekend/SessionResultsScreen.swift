import SwiftUI

struct SessionResultsScreen: View {
    let api: WeekendAPI
    let weekend: Weekend
    @State var selected: String
    @State private var rows: [ClassificationRow] = []
    @State private var loading = false
    @State private var message: String?
    @State private var attempt = 0
    @State private var generation = UUID()

    private var session: WeekendSession? { weekend.sessions.first { $0.code == selected } }
    private var group: String {
        if selected.hasPrefix("practice") { return "practice" }
        if selected.hasPrefix("sprint") { return "sprint" }
        return "weekend"
    }
    private var groups: [(String, String, [WeekendSession])] {
        [("practice", "Практика", weekend.orderedSessions.filter { $0.code.hasPrefix("practice") }),
         ("sprint", "Спринт", weekend.orderedSessions.filter { $0.code.hasPrefix("sprint") }),
         ("weekend", "Уик-энд", weekend.orderedSessions.filter { ["qualifying", "race"].contains($0.code) })]
            .filter { !$0.2.isEmpty }
    }

    var body: some View {
        List {
            Section {
                Text(weekend.event?.name ?? "Этап").font(.title2.bold())
                Text("\(String(weekend.season)) · этап \(weekend.event?.round ?? 0)").foregroundStyle(TurboTheme.muted)
                Picker("Раздел результатов", selection: Binding(get: { group }, set: { value in
                    if let first = groups.first(where: { $0.0 == value })?.2.first { selected = first.code }
                })) {
                    ForEach(groups, id: \.0) { item in Text(item.1).tag(item.0) }
                }
                Picker("Сессия", selection: $selected) {
                    ForEach(groups.first { $0.0 == group }?.2 ?? [], id: \.code) { Text($0.title).tag($0.code) }
                }
            }.listRowBackground(TurboTheme.surface)
            Section(session?.title ?? "Результаты") {
                if session?.canOpenResults(at: Date()) != true {
                    Text("Результаты этой сессии пока недоступны. Выберите прошедшую сессию.")
                } else if loading {
                    ProgressView("Загружаем классификацию…")
                } else if let message {
                    Text(message)
                    Button("Повторить загрузку") { attempt += 1 }.frame(minHeight: 44)
                } else if rows.isEmpty {
                    Text("Классификация выбранной сессии ещё не опубликована. Источник может обновить её с задержкой после финиша.")
                } else {
                    ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                        HStack(alignment: .top, spacing: 14) {
                            Text(session?.practice != nil ? String(index + 1) : row.position.map { $0 > 0 ? String($0) : "—" } ?? "—").font(.title3.bold()).monospacedDigit().frame(minWidth: 28)
                            VStack(alignment: .leading, spacing: 5) {
                                Text(row.displayName).font(.headline)
                                if let team = row.team { Text(team).font(.subheadline).foregroundStyle(TurboTheme.muted) }
                                Text(details(row)).font(.subheadline).monospacedDigit()
                                if let laps = row.laps { Text("Круги: \(laps)").font(.footnote).foregroundStyle(TurboTheme.muted) }
                            }
                            Spacer(minLength: 0)
                            if let points = row.points { Text("\(points.formatted()) очк.").font(.subheadline).monospacedDigit() }
                        }.padding(.vertical, 6).accessibilityElement(children: .combine)
                    }
                }
            }.listRowBackground(TurboTheme.surface)
        }
        .foregroundStyle(TurboTheme.ink)
        .scrollContentBackground(.hidden).background(TurboTheme.background)
        .navigationTitle("Результаты").navigationBarTitleDisplayMode(.inline)
        .task(id: "\(selected):\(attempt)") { await load() }
        .refreshable { await load() }
    }

    private func details(_ row: ClassificationRow) -> String {
        let time = row.best ?? row.time ?? row.status ?? "—"
        var gap = row.gap
        if session?.practice != nil, let best = SessionClassification.lapSeconds(row.best),
           let leader = SessionClassification.lapSeconds(rows.first?.best) {
            gap = best == leader ? "—" : String(format: "+%.3f", best - leader)
        }
        return [time, gap, row.segment].compactMap { $0 }.joined(separator: " · ")
    }

    @MainActor private func load() async {
        guard let session, let event = weekend.event, session.canOpenResults(at: Date()) else { return }
        let key = selected
        let token = UUID()
        generation = token
        loading = true
        rows = []
        message = nil
        defer { if key == selected, generation == token { loading = false } }
        do {
            let result = try await api.classification(season: weekend.season, round: event.round, session: session)
            try Task.checkCancellation()
            if key == selected, generation == token { rows = result }
        } catch {
            guard !Task.isCancelled, key == selected, generation == token else { return }
            message = "Не удалось загрузить результаты. Проверьте соединение и повторите загрузку."
        }
    }
}
