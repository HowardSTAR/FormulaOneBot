import SwiftUI

struct CircuitProfileSheet: View {
    let api: WeekendAPI
    let weekend: Weekend
    @Environment(\.dismiss) private var dismiss
    @State private var profile: CircuitProfile?
    @State private var loading = true
    @State private var failed = false
    @State private var stale = false
    @State private var attempt = 0

    var body: some View {
        NavigationStack {
            List {
                if loading { ProgressView("Загружаем статистику трассы…") }
                else if let profile {
                    Section {
                        Text(profile.name).font(.title2.bold())
                        if stale { Label("Данные могут быть устаревшими", systemImage: "clock") }
                        if let updated = profile.updatedAt { Text("Обновлено: \(updated)").font(.footnote) }
                    }
                    if !profile.compounds.isEmpty {
                        Section("Номинированные составы") {
                            ForEach(Array(profile.compounds.enumerated()), id: \.offset) { _, compound in Text(compound) }
                        }
                    }
                    if !profile.ratings.isEmpty {
                        Section("Характер трассы") {
                            ForEach(Array(profile.ratings.enumerated()), id: \.offset) { _, rating in
                                LabeledContent(rating.label, value: "\(rating.value) из 5")
                            }
                        }
                    }
                    Section("История") {
                        if let team = profile.team { LabeledContent("Команда: \(team.name)", value: "\(team.wins) побед") }
                        if let driver = profile.driver { LabeledContent("Пилот: \(driver.name)", value: "\(driver.wins) побед") }
                        if let year = profile.firstRace { LabeledContent("Первая гонка F1", value: String(year)) }
                        if let year = profile.opened { LabeledContent("Открытие трассы", value: String(year)) }
                        if let year = profile.historyThrough { Text("История по \(String(year)) год включительно").font(.footnote) }
                        if let record = profile.lapRecord {
                            Text("Быстрейший круг базы: \(record.time) · \(record.driver) · \(String(record.year))")
                            Text("Данные с 2004 года могут включать прежние конфигурации трассы.").font(.footnote).foregroundStyle(TurboTheme.muted)
                        }
                    }
                    if profile.pressures != nil || profile.pitLoss != nil {
                        Section("Дополнительно") {
                            if let pit = profile.pitLoss { LabeledContent("Потеря на пит-стопе", value: pit) }
                            if let pressure = profile.pressures {
                                LabeledContent("Передние шины", value: pressure.front)
                                LabeledContent("Задние шины", value: pressure.rear)
                            }
                        }
                    }
                    Section("Источники") {
                        ForEach(Array(profile.sources.enumerated()), id: \.offset) { _, source in
                            if let url = URL(string: source.href), ["https", "http"].contains(url.scheme) {
                                Link(source.title, destination: url)
                            }
                        }
                    }
                } else {
                    Text(failed ? "Не удалось загрузить статистику трассы." : "Подтверждённых данных этого этапа пока нет.")
                    Button("Повторить загрузку") { attempt += 1 }
                }
            }
            .scrollContentBackground(.hidden).background(TurboTheme.background)
            .foregroundStyle(TurboTheme.ink).tint(TurboTheme.accent)
            .navigationTitle("Статистика трассы").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Закрыть") { dismiss() } } }
            .task(id: attempt) { await load() }
        }.presentationDragIndicator(.visible)
    }

    @MainActor private func load() async {
        guard let event = weekend.event else { loading = false; return }
        loading = true; failed = false
        defer { loading = false }
        do {
            let response: CircuitProfileResponse = try await api.data(path: "api/circuit-profile", query: [
                .init(name: "season", value: String(weekend.season)), .init(name: "round", value: String(event.round))])
            try Task.checkCancellation()
            profile = response.matching(weekend)
            stale = response.status == "stale" || profile?.stale == true
        } catch { if !Task.isCancelled { failed = true } }
    }
}
