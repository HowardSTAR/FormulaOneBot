import SwiftUI

// Exact semantic token values from front/src/assets/design-system.css.
enum TurboTheme {
    static let background = adaptive(0xf5f5f7, 0x141518)
    static let surface = adaptive(0xffffff, 0x202125)
    static let ink = adaptive(0x202126, 0xf2f2f4)
    static let muted = adaptive(0x64666e, 0xb0b1ba)
    static let line = adaptive(0xdedfe3, 0x393b42)
    static let accent = adaptive(0xb92b25, 0xff9b92)
    static let supporter = adaptive(0x805300, 0xedc975)
    static let tint = adaptive(0xfaeeec, 0x382522)

    private static func adaptive(_ light: UInt32, _ dark: UInt32) -> Color {
        Color(uiColor: UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((hex >> 16) & 255) / 255,
                           green: CGFloat((hex >> 8) & 255) / 255,
                           blue: CGFloat(hex & 255) / 255, alpha: 1)
        })
    }
}
