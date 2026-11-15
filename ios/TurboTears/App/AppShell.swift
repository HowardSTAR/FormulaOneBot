import SwiftUI

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
