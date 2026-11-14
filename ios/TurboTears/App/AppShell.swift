import SwiftUI
import CryptoKit

struct AppShell: View {
    @Binding var address: String
    let baseURL: URL
    @AppStorage("appearance") private var appearance = "system"
    @State private var tab = 0
    @State private var settings = false

    init(address: Binding<String>, baseURL: URL) {
        _address = address
        self.baseURL = baseURL
        #if DEBUG
        let previewTab = Int(ProcessInfo.processInfo.environment["TURBOTEARS_PREVIEW_TAB"] ?? "0") ?? 0
        _tab = State(initialValue: (0...2).contains(previewTab) ? previewTab : 0)
        #endif
    }

    var body: some View {
        TabView(selection: $tab) {
            Tab("Обзор", systemImage: "house.fill", value: 0) {
                HomeScreen(baseURL: baseURL) { tab = 1 }
            }
            Tab("Уик-энд", systemImage: "flag.checkered", value: 1) {
                WeekendScreen(baseURL: baseURL, address: $address)
            }
            Tab("Меню", systemImage: "line.3.horizontal", value: 2) {
                NavigationStack {
                    List {
                        Section("Гонки") {
                            Button("Уик-энд", systemImage: "flag.checkered") { tab = 1 }.frame(minHeight: 44)
                        }
                        Section("Оформление") {
                            Picker("Тема", selection: $appearance) {
                                Text("Как на устройстве").tag("system")
                                Text("Светлая").tag("light")
                                Text("Тёмная").tag("dark")
                            }
                        }
                        Section("Приложение") {
                            Button("Сервер API", systemImage: "network") { settings = true }.frame(minHeight: 44)
                            Link("Источники данных", destination: baseURL.appending(path: "about/data"))
                            Link("Конфиденциальность", destination: baseURL.appending(path: "privacy"))
                        }
                    }
                    .scrollContentBackground(.hidden).background(TurboTheme.background)
                    .navigationTitle("Меню")
                    .sheet(isPresented: $settings) { ServerSettings(address: $address) }
                }
            }
        }
        .tint(TurboTheme.accent).foregroundStyle(TurboTheme.ink)
        .preferredColorScheme(appearance == "system" ? nil : appearance == "dark" ? .dark : .light)
    }
}

private struct HomeScreen: View {
    @State private var store: WeekendStore
    private let api: WeekendAPI
    let openWeekend: () -> Void
    private let selection = WeekendSelection(season: Calendar.current.component(.year, from: Date()))

    init(baseURL: URL, openWeekend: @escaping () -> Void) {
        let key = SHA256.hash(data: Data(baseURL.absoluteString.utf8)).map { String(format: "%02x", $0) }.joined()
        _store = State(initialValue: WeekendStore(api: WeekendAPI(baseURL: baseURL),
            cache: WeekendCache(directory: URL.cachesDirectory.appending(path: "TurboTears/Weekends/\(key)"))))
        self.api = WeekendAPI(baseURL: baseURL)
        self.openWeekend = openWeekend
    }

    var body: some View {
        NavigationStack {
            List {
                if store.isCached {
                    Label("Сохранённая копия", systemImage: "internaldrive")
                }
                if let message = store.message {
                    Section {
                        Text(message)
                        Button("Повторить загрузку") { Task { await store.load(selection) } }.disabled(store.isLoading)
                    }
                }
                if let weekend = store.weekend, let event = weekend.event {
                    Section {
                        VStack(alignment: .leading, spacing: 12) {
                            Text(event.name).font(.largeTitle.bold()).fixedSize(horizontal: false, vertical: true)
                            Text([event.location, event.country].compactMap { $0 }.joined(separator: " · "))
                                .foregroundStyle(TurboTheme.muted)
                            Text("Этап \(event.round) · \(String(weekend.season))").font(.subheadline)
                            if event.isCancelled {
                                Label("Этап отменён", systemImage: "calendar.badge.minus")
                            } else if let start = weekend.raceStart {
                                Text("Старт гонки").font(.subheadline).foregroundStyle(TurboTheme.muted)
                                Text(start, format: .dateTime.day().month(.wide).hour().minute())
                                    .font(.title2.weight(.semibold)).monospacedDigit()
                            }
                            Button("Открыть уик-энд", systemImage: "flag.checkered", action: openWeekend)
                                .buttonStyle(.borderedProminent)
                                .tint(Color(red: 185/255, green: 43/255, blue: 37/255))
                                .foregroundStyle(.white).frame(minHeight: 44)
                        }.padding(.vertical, 12)
                    }.listRowBackground(TurboTheme.surface)
                    if !event.isCancelled {
                        Section("Следующая сессия") {
                          TimelineView(.periodic(from: .now, by: 30)) { timeline in
                            if let index = weekend.nextSessionIndex(at: timeline.date) {
                                let next = weekend.orderedSessions[index]
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(next.title).font(.title3.bold())
                                    if let date = next.startsAt {
                                        Text(date, format: .dateTime.weekday(.wide).day().month().hour().minute())
                                        if date.timeIntervalSince(timeline.date) < 7 * 86400 {
                                            Text(date, style: .relative).monospacedDigit().foregroundStyle(TurboTheme.accent)
                                                .accessibilityLabel("До начала сессии")
                                        }
                                    }
                                }.frame(maxWidth: .infinity, alignment: .leading)
                            } else { Text("Следующая сессия пока не объявлена.") }
                          }
                        }.listRowBackground(TurboTheme.tint)
                    }
                } else if store.isLoading {
                    ProgressView("Загружаем уик-энд…")
                } else if let weekend = store.weekend {
                    ContentUnavailableView(weekend.status == "season_finished" ? "Сезон завершён" : "Расписание недоступно",
                        systemImage: "calendar", description: Text("Архивный этап можно выбрать в разделе «Уик-энд»."))
                    Button("Выбрать этап", action: openWeekend)
                }
                HomeStandings(api: api, season: selection.season)
            }
            .navigationTitle("TurboTears")
            .scrollContentBackground(.hidden).background(TurboTheme.background)
            .task { await store.load(selection) }
            .refreshable { await store.load(selection) }
        }
    }
}
