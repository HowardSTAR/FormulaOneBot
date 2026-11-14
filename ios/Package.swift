// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "TurboTearsCore",
    platforms: [.macOS(.v14), .iOS(.v26)],
    products: [.library(name: "TurboTearsCore", targets: ["TurboTearsCore"])],
    targets: [
        .target(name: "TurboTearsCore", path: "TurboTears/Core"),
        .testTarget(name: "TurboTearsCoreTests", dependencies: ["TurboTearsCore"], path: "Tests")
    ]
)
