# F1 Hub Playwright tests

API and UI automation against [https://f1hub.ru](https://f1hub.ru).

## Setup

```bash
npm install
```

For UI tests, install Chromium once:

```bash
npx playwright install chromium
```

## Run

Always from this folder (`tests/Playwright`), not from `tests/ui` or the repo root — otherwise `playwright.config.ts` (and `baseURL`) is not loaded and `page.goto("/")` fails.

```bash
cd FormulaOneBot/tests/Playwright
npm run test:api
npm run test:ui
```

UI / debug:

```bash
npx playwright test --ui
npx playwright test tests/ui/home.spec.ts --debug
```

Base URL comes from `.env` next to `playwright.config.ts`:

```env
BASE_URL=https://f1hub.ru
```

Or override in PowerShell:

```powershell
$env:BASE_URL="https://f1hub.ru"; npm run test:api
```

## Scope (current)

- Public **GET** endpoints: health, standings, calendar, results, details, compare, media
- Auth **guards** on protected GETs (expect `401 missing_session`)
- UI smoke: home brand (`F1 Hub` + `Race intelligence`)
- No registration / login / mutations against production
