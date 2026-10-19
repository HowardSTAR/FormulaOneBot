# Telegram Web App SDK

`telegram-web-app.js` is an unmodified snapshot of the official SDK from
https://telegram.org/js/telegram-web-app.js, retrieved on 2026-10-19.

SHA-256 of the downloaded bytes, before Git line-ending normalization:
`124bdff7ba3fe86c8ba5143467afec21e020405e74abdb92cfdda6c0ee3b5908`.

Serve the SDK from our origin so a blocked Telegram domain cannot prevent the
website from starting. Keep the script synchronous before the app's module entry:
Telegram init data must be available before React mounts. When updating, fetch
the official SDK, update the checksum here, and run the startup resilience check.
