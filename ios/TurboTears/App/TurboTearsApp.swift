import SwiftUI

@main
struct TurboTearsApp: App {
    @AppStorage("apiBaseURL") private var baseURL = "https://new.f1hub.ru"

    init() {
        let defaults = UserDefaults.standard
        if defaults.integer(forKey: "serverConfigurationVersion") < 2 {
            defaults.set("https://new.f1hub.ru", forKey: "apiBaseURL")
            defaults.set(2, forKey: "serverConfigurationVersion")
        }
    }

    var body: some Scene {
        WindowGroup {
            if let url = URL(string: baseURL) {
                AppShell(address: $baseURL, baseURL: url)
                    .id(baseURL)
            }
        }
    }
}
