# Local fonts

Unmodified WOFF2 subsets for Inter (variable weights 400–800) and Space Grotesk
(500–700), retrieved from Google Fonts on 2026-10-19. `../fonts.css` maps the
original Unicode ranges to local files. Vite fingerprints the fonts with the CSS.
All original script subsets are retained; Space Grotesk has no Cyrillic subset.

Source stylesheet:
https://fonts.googleapis.com/css2?family=Inter:wght@400..800&family=Space+Grotesk:wght@500..700&display=swap

Licenses: `Inter-OFL.txt` and `SpaceGrotesk-OFL.txt`, from the respective
`ofl/inter` and `ofl/spacegrotesk` directories of https://github.com/google/fonts.

The app uses `font-display: swap` and has no runtime dependency on Google Fonts.
