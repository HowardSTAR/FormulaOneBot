import SwiftUI

struct HomeStandings: View {
    let api: WeekendAPI
    let season: Int
    @State private var category = "drivers"
    @State private var rows: [StandingRow] = []
    @State private var loading = true
    @State private var failed = false
    @State private var attempt = 0

    var body: some View {
        Section("Чемпионат \(String(season))") {
            Picker("Зачёт", selection: $category) {
                Text("Пилоты").tag("drivers")
                Text("Команды").tag("constructors")
            }.pickerStyle(.segmented)
            if loading { ProgressView("Загружаем зачёт…") }
            else if failed {
                Text("Не удалось загрузить очки.")
                Button("Повторить загрузку зачёта") { attempt += 1 }
            } else if rows.isEmpty { Text("Результаты сезона ещё не опубликованы.") }
            else {
                ForEach(Array(rows.prefix(5).enumerated()), id: \.offset) { _, row in
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        Text(String(row.position)).monospacedDigit().font(.headline)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(row.name).font(.headline)
                            if let team = row.constructorName { Text(team).font(.footnote).foregroundStyle(TurboTheme.muted) }
                        }
                        Spacer(minLength: 0)
                        VStack(alignment: .trailing, spacing: 4) {
                            Text(row.points.map { "\($0.formatted()) очк." } ?? "—").monospacedDigit()
                            if let leader = rows.first?.points, let points = row.points, leader >= points {
                                Text(row.position == 1 ? "Лидер" : "−\((leader - points).formatted())")
                                    .font(.footnote).foregroundStyle(TurboTheme.muted).monospacedDigit()
                            }
                        }
                    }.padding(.vertical, 4).accessibilityElement(children: .combine)
                }
            }
        }
        .listRowBackground(TurboTheme.surface)
        .task(id: "\(category):\(season):\(attempt)") { await load() }
    }

    @MainActor private func load() async {
        let key = category
        loading = true; failed = false; rows = []
        defer { if category == key { loading = false } }
        do {
            let response: StandingsResponse = try await api.data(path: "api/\(key)", query: [.init(name: "season", value: String(season))])
            try Task.checkCancellation()
            guard key == category else { return }
            if let returnedSeason = response.season, returnedSeason != season { return }
            rows = (key == "drivers" ? response.drivers : response.constructors) ?? []
        } catch { if key == category, !Task.isCancelled { failed = true } }
    }
}
