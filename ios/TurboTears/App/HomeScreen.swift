import SwiftUI
import CryptoKit

struct HomeScreen: View {
    @State private var store: WeekendStore
    @State private var expanded = false
    @State private var section = "season"
    @Environment(\.dynamicTypeSize) private var typeSize
    let api: WeekendAPI
    let openWeekend: () -> Void
    private let selection = WeekendSelection(season: Calendar.current.component(.year, from: Date()))

    init(baseURL: URL, openWeekend: @escaping () -> Void) {
        let key = SHA256.hash(data: Data(baseURL.absoluteString.utf8)).map { String(format: "%02x", $0) }.joined()
        let api = WeekendAPI(baseURL: baseURL)
        _store = State(initialValue: WeekendStore(api: api,
            cache: WeekendCache(directory: URL.cachesDirectory.appending(path: "TurboTears/Weekends/\(key)"))))
        self.api = api
        self.openWeekend = openWeekend
        #if DEBUG
        _expanded = State(initialValue: ProcessInfo.processInfo.environment["TURBOTEARS_PREVIEW_SCHEDULE"] == "expanded")
        #endif
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if store.isCached { Label("Сохранённая копия", systemImage: "internaldrive").font(.footnote) }
                    if let message = store.message {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(message).font(.subheadline)
                            Button("Повторить загрузку") { Task { await store.load(selection) } }
                                .buttonStyle(HomePillStyle()).disabled(store.isLoading)
                        }.homePanel()
                    }
                    if section == "season" {
                        overview
                    } else {
                        featureSection
                    }
                }
                .frame(maxWidth: 760)
                .padding(.horizontal, 16).padding(.vertical, 12)
                .frame(maxWidth: .infinity)
            }
            .background(TurboTheme.background)
            .foregroundStyle(TurboTheme.ink)
            .toolbar(.hidden, for: .navigationBar)
            .task { await store.load(selection) }
            .refreshable { await store.load(selection) }
        }
    }

    private var sectionSwitch: some View {
        LiquidGlassSwitch(title: "Разделы главной", options: [
            .init(id: "season", title: "Сезон", symbol: "house"),
            .init(id: "games", title: "Игры", symbol: "gamecontroller"),
            .init(id: "guide", title: "Справка", symbol: "book"),
            .init(id: "subscription", title: "Поддержка проекта", symbol: "supporter")
        ], selection: $section, iconsOnly: true)
        .frame(maxWidth: typeSize.isAccessibilitySize ? .infinity : 280)
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder private var overview: some View {
        if let weekend = store.weekend, let event = weekend.event {
            raceHero(weekend, event)
            sectionSwitch
            schedule(weekend)
        } else {
            VStack(alignment: .leading, spacing: 12) {
                if store.isLoading { ProgressView("Загружаем уик-энд…") }
                else {
                    Text(store.weekend?.status == "season_finished" ? "Сезон завершён" : "Расписание недоступно")
                        .font(.title2.bold())
                    Text("Результаты прошедших этапов можно выбрать в разделе «Уик-энд».")
                        .font(.subheadline).foregroundStyle(TurboTheme.muted)
                    Button("Выбрать этап", action: openWeekend).buttonStyle(HomePillStyle())
                }
            }.homePanel()
            sectionSwitch
        }
        HomeStandings(api: api, season: store.weekend?.season ?? selection.season)
        VStack(spacing: 0) {
            Link(destination: pastResultsURL) {
                shortcut("Результаты сессий", symbol: "list.number", external: true)
            }.accessibilityHint("Архив откроется на сайте")
            Divider().overlay(TurboTheme.line)
            Link(destination: api.baseURL.appending(path: "wiki")) {
                shortcut("Как устроен чемпионат", symbol: "questionmark.circle", external: true)
            }
        }.homePanel(padding: 0)
    }

    private func raceHero(_ weekend: Weekend, _ event: WeekendEvent) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 16))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 12))
        return VStack(alignment: .leading, spacing: 18) {
            Text(event.name).font(.title.bold())
                .fixedSize(horizontal: false, vertical: true)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 14) { location(event); Text("Этап \(event.round)").font(.footnote).foregroundStyle(TurboTheme.muted) }
                VStack(alignment: .leading, spacing: 5) { location(event); Text("Этап \(event.round)").font(.footnote) }
            }
            if event.isCancelled {
                Label("Этап отменён", systemImage: "calendar.badge.minus").font(.headline)
            } else {
                layout {
                    VStack(alignment: .leading, spacing: 7) {
                        Text("Старт гонки").font(.footnote).foregroundStyle(TurboTheme.muted)
                        if let start = weekend.raceStart {
                            Text(start, format: .dateTime.weekday(.abbreviated).day().month(.wide)).font(.subheadline.weight(.semibold))
                            Text(start, format: .dateTime.hour().minute())
                                .font(.system(.largeTitle, design: .default, weight: .semibold))
                                .monospacedDigit().foregroundStyle(TurboTheme.accent).fixedSize()
                        } else { Text("Время уточняется").font(.headline) }
                        Text(timezoneLabel).font(.caption).foregroundStyle(TurboTheme.muted)
                    }.layoutPriority(1)
                    Button(action: openWeekend) {
                        RaceCircuitMap(event: event, season: weekend.season, baseURL: api.baseURL)
                            .frame(maxWidth: .infinity).frame(height: 155)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Открыть уик-энд: \(event.name)")
                }.padding(.top, 4)
            }
            TimelineView(.periodic(from: .now, by: 30)) { timeline in
                Label(countdown(weekend.raceStart, now: timeline.date, cancelled: event.isCancelled), systemImage: "clock")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(TurboTheme.ink)
            }
        }
        .padding(.horizontal, 4).padding(.vertical, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background { RaceFlagBackground(event: event, baseURL: api.baseURL) }
    }

    private var timezoneLabel: String {
        let zone = TimeZone.current
        let seconds = zone.secondsFromGMT()
        let hours = seconds / 3600, minutes = abs(seconds % 3600) / 60
        let offset = "UTC\(seconds >= 0 ? "+" : "−")\(abs(hours))" + (minutes > 0 ? String(format: ":%02d", minutes) : "")
        return zone.identifier == "Europe/Moscow" ? "МСК (\(offset))" : "\(zone.abbreviation() ?? zone.identifier) (\(offset))"
    }

    private func location(_ event: WeekendEvent) -> some View {
        Text([event.location, event.country].compactMap { $0 }.joined(separator: " · "))
            .font(.subheadline).foregroundStyle(TurboTheme.muted)
    }

    private func schedule(_ weekend: Weekend) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            DisclosureGroup(isExpanded: $expanded) {
                VStack(alignment: .leading, spacing: 0) {
                    Text("Время на устройстве: \(TimeZone.current.identifier)")
                        .font(.caption).foregroundStyle(TurboTheme.muted).padding(.vertical, 12)
                    if weekend.event?.isCancelled == true {
                        Text("Этап отменён. Сессии не состоятся.").font(.subheadline)
                    } else if weekend.orderedSessions.isEmpty {
                        Text("Подробное расписание пока недоступно.").font(.subheadline)
                        Button("Обновить расписание") { Task { await store.load(selection) } }
                            .buttonStyle(HomePillStyle()).disabled(store.isLoading).padding(.top, 10)
                    } else {
                        TimelineView(.periodic(from: .now, by: 30)) { timeline in
                            VStack(spacing: 0) {
                                ForEach(Array(weekend.orderedSessions.enumerated()), id: \.offset) { index, session in
                                    if index > 0 { Divider().overlay(TurboTheme.line) }
                                    Button(action: openWeekend) {
                                        HStack(spacing: 12) {
                                            VStack(alignment: .leading, spacing: 3) {
                                                Text(session.title).font(.subheadline.weight(.semibold))
                                                if weekend.nextSessionIndex(at: timeline.date) == index {
                                                    Text("Ближайшая сессия").font(.caption).foregroundStyle(TurboTheme.accent)
                                                }
                                            }
                                            Spacer(minLength: 6)
                                            if let start = session.startsAt {
                                                VStack(alignment: .trailing, spacing: 3) {
                                                    Text(start, format: .dateTime.day().month(.abbreviated)).font(.caption).foregroundStyle(TurboTheme.muted)
                                                    Text(start, format: .dateTime.hour().minute()).font(.subheadline.weight(.semibold)).monospacedDigit()
                                                }
                                            } else { Text("Время уточняется").font(.caption) }
                                        }.padding(.vertical, 12).frame(minHeight: 44)
                                    }.buttonStyle(.plain)
                                }
                            }
                        }
                    }
                }
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "calendar").foregroundStyle(TurboTheme.accent)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Расписание уик-энда").font(.subheadline.weight(.semibold))
                        TimelineView(.periodic(from: .now, by: 30)) { timeline in
                            if let index = weekend.nextSessionIndex(at: timeline.date), weekend.event?.isCancelled != true {
                                let next = weekend.orderedSessions[index]
                                Text(next.title + (next.startsAt.map { " · " + $0.formatted(.dateTime.day().month(.abbreviated).hour().minute()) } ?? ""))
                                    .font(.caption).foregroundStyle(TurboTheme.muted)
                            } else { Text("Даты, время и все сессии этапа").font(.caption).foregroundStyle(TurboTheme.muted) }
                        }
                    }
                }.frame(minHeight: 44)
            }.tint(TurboTheme.muted)
        }.homePanel()
    }

    private func shortcut(_ title: String, symbol: String, external: Bool) -> some View {
        HStack(spacing: 12) {
            Image(systemName: symbol).foregroundStyle(TurboTheme.accent)
            Text(title).font(.subheadline.weight(.medium))
            Spacer(minLength: 0)
            Image(systemName: external ? "arrow.up.right" : "chevron.right").font(.caption).foregroundStyle(TurboTheme.muted)
        }.foregroundStyle(TurboTheme.ink).padding(16).frame(minHeight: 52)
    }

    private var featureSection: some View {
        VStack(alignment: .leading, spacing: 18) {
            sectionSwitch
            VStack(alignment: .leading, spacing: 12) {
                Text(section == "games" ? "Ваш прогноз. Следующий подиум." : section == "subscription" ? "Поддержите TurboTears" : "Что улучшим в TurboTears?")
                    .font(.title2.bold())
                Text(section == "games" ? "Выберите свою тройку на гонку и соревнуйтесь с друзьями в зачёте прогнозов." : section == "subscription" ? "Новости проекта и способы поддержки — на странице TurboTears." : "Предложите идею или сообщите об ошибке.")
                    .font(.subheadline).foregroundStyle(TurboTheme.muted)
                if section == "subscription" {
                    Link("TurboTears на Boosty", destination: URL(string: "https://boosty.to/turbotears")!).buttonStyle(HomePillStyle())
                } else {
                    Link(section == "games" ? "Сделать прогноз на сайте" : "Написать отзыв на сайте",
                         destination: api.baseURL.appending(path: section == "games" ? "predictions" : "contact-admin"))
                        .buttonStyle(HomePillStyle())
                }
            }.homePanel()
            if section == "games" {
                webShortcut("Тест реакции", path: "reaction-game", symbol: "bolt")
                webShortcut("Reflex Grid", path: "reflex-grid-game", symbol: "square.grid.3x3")
                webShortcut("Emerald Loop", path: "race-game", symbol: "steeringwheel")
            } else if section == "guide" {
                webShortcut("История чемпионата", path: "history", symbol: "clock.arrow.circlepath")
                webShortcut("Справочник F1", path: "wiki", symbol: "book")
            }
        }
    }

    private var pastResultsURL: URL {
        var components = URLComponents(url: api.baseURL.appending(path: "season"), resolvingAgainstBaseURL: false)!
        components.queryItems = [.init(name: "filter", value: "past")]
        return components.url!
    }

    private func webShortcut(_ title: String, path: String, symbol: String) -> some View {
        Link(destination: api.baseURL.appending(path: path)) { shortcut(title, symbol: symbol, external: true) }
            .homePanel(padding: 0).accessibilityHint("Откроется на сайте")
    }

    private func countdown(_ date: Date?, now: Date, cancelled: Bool) -> String {
        if cancelled { return "Этап отменён организатором" }
        guard let date else { return "Время старта уточняется" }
        guard date > now else { return "Плановое время старта прошло" }
        let minutes = Int(ceil(date.timeIntervalSince(now) / 60))
        let days = minutes / 1440, hours = (minutes % 1440) / 60, rest = minutes % 60
        return "Через " + [days > 0 ? "\(days) д" : nil, hours > 0 ? "\(hours) ч" : nil,
                           rest > 0 || (days == 0 && hours == 0) ? "\(rest) мин" : nil].compactMap { $0 }.joined(separator: " ")
    }
}

struct HomePillStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(TurboTheme.ink)
            .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 44)
            .background(configuration.isPressed ? TurboTheme.tint : TurboTheme.surface, in: Capsule())
            .overlay(Capsule().strokeBorder(TurboTheme.line))
    }
}

extension View {
    func homePanel(padding: CGFloat = 16) -> some View {
        self.padding(padding).frame(maxWidth: .infinity, alignment: .leading)
            .background(TurboTheme.surface, in: RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(TurboTheme.line))
    }
}
