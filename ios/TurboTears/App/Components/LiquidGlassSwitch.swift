import SwiftUI

struct GlassSwitchOption: Identifiable {
    let id: String
    let title: String
    var symbol: String? = nil
}

/// A material rail and one native refractive glass lens. No opaque selection imitation.
struct LiquidGlassSwitch: View {
    let title: String
    let options: [GlassSwitchOption]
    @Binding var selection: String
    var iconsOnly = false
    @Namespace private var glass
    @State private var width: CGFloat = 0
    @GestureState private var preview: String?
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.layoutDirection) private var direction
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var current: String { preview ?? selection }
    private var opaque: Bool { reduceTransparency || contrast == .increased }
    private var animation: Animation? { reduceMotion ? nil : .snappy(duration: 0.25) }
    private var shape: AnyShape { typeSize.isAccessibilitySize ? AnyShape(RoundedRectangle(cornerRadius: 26)) : AnyShape(Capsule()) }

    var body: some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(spacing: 4)) : AnyLayout(HStackLayout(spacing: 0))
        GlassEffectContainer(spacing: 0) {
            layout {
                ForEach(options) { option in
                    Button { withAnimation(animation) { selection = option.id } } label: {
                        if current == option.id && !opaque {
                            segmentLabel(option)
                                .glassEffect(.regular.interactive(), in: Capsule())
                                .glassEffectID("selection", in: glass)
                                .glassEffectTransition(.matchedGeometry)
                        } else {
                            segmentLabel(option).background {
                                if current == option.id {
                                    Capsule().fill(TurboTheme.tint).overlay(Capsule().strokeBorder(TurboTheme.ink))
                                }
                            }
                        }
                    }
                    .buttonStyle(SegmentPressStyle())
                    .accessibilityLabel(option.title)
                    .accessibilityAddTraits(selection == option.id ? .isSelected : [])
                }
            }.padding(4)
        }
        .background {
            if opaque { shape.fill(TurboTheme.surface) }
            else { shape.fill(.regularMaterial) }
        }
        .overlay(shape.stroke(TurboTheme.line, lineWidth: 1))
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
        .simultaneousGesture(DragGesture(minimumDistance: 12)
            .updating($preview) { value, state, transaction in
                state = candidate(value); transaction.animation = animation
            }
            .onEnded { value in
                if let id = candidate(value) { withAnimation(animation) { selection = id } }
            })
        .accessibilityElement(children: .contain).accessibilityLabel(title)
    }

    private func candidate(_ value: DragGesture.Value) -> String? {
        guard !typeSize.isAccessibilitySize, !options.isEmpty, width > 8,
              abs(value.translation.width) > abs(value.translation.height) * 1.4 else { return nil }
        let index = min(options.count - 1, max(0, Int(floor((value.location.x - 4) / ((width - 8) / CGFloat(options.count))))))
        return options[direction == .rightToLeft ? options.count - 1 - index : index].id
    }

    private func segmentLabel(_ option: GlassSwitchOption) -> some View {
        label(option).padding(.horizontal, 8).frame(maxWidth: .infinity, minHeight: 44)
            .foregroundStyle(current == option.id ? TurboTheme.accent : TurboTheme.ink)
            .contentShape(Capsule())
    }

    private func label(_ option: GlassSwitchOption) -> some View {
        HStack(spacing: 8) {
            if let symbol = option.symbol {
                if symbol == "supporter" {
                    SupporterMark().stroke(TurboTheme.supporter, lineWidth: 1.3).frame(width: 24, height: 24)
                } else { Image(systemName: symbol).font(.title3) }
            }
            if !iconsOnly || typeSize.isAccessibilitySize {
                Text(option.title).font(.subheadline.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

private struct SegmentPressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.opacity(configuration.isPressed ? 0.65 : 1)
    }
}
