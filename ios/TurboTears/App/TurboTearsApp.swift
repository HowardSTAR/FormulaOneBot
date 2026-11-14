import SwiftUI

@main
struct TurboTearsApp: App {
    @AppStorage("apiBaseURL") private var baseURL = "http://localhost:8000"

    var body: some Scene {
        WindowGroup {
            if let url = URL(string: baseURL) {
                AppShell(address: $baseURL, baseURL: url)
                    .id(baseURL)
            }
        }
    }
}
