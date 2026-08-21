# Legal deployment checklist

This checklist separates completed code changes from external actions that cannot be completed inside the repository. It is an engineering record, not an individual legal opinion.

## Completed in code

- Product-facing brand changed to TurboTears.
- Visible unofficial-service and trade-mark disclaimer added to the global footer.
- `/privacy`, `/terms`, `/legal/ip`, `/about/data` and `/account/delete` added.
- Authenticated account deletion with password and explicit confirmation added.
- Privacy/IP requests accepted through the contact form.
- Data-source limitations and non-commercial status documented.
- MIT source-code license, third-party notices and asset register added.
- Inter and Space Grotesk confirmed as open-font choices in frontend code.

## Production blockers requiring operator input

- Set real `LEGAL_OPERATOR_NAME`, `LEGAL_OPERATOR_ADDRESS`, `LEGAL_CONTACT_EMAIL` and `DATA_STORAGE_LOCATION` before building the frontend. Generic fallback text is not a substitute for actual operator details.
- Approve and implement exact retention periods for activity logs, feedback, audit records and backups. Do not enable destructive scheduled cleanup until backup, incident-response and legal-retention requirements are reconciled.
- Confirm that the primary database used to collect Russian citizens' personal data meets applicable localization rules and document every processor and cross-border transfer.
- Determine whether the operator must notify Roskomnadzor before processing and file/update the notification where required.
- Register the production `/privacy` URL in BotFather and update the bot/Mini App title and descriptions to TurboTears.

## External rename and rollout

- Rename the public GitHub repository from `FormulaOneBot` to `TurboTears` and update remote URLs, badges, webhooks and CI credentials.
- Move the public site from any F1-branded domain to a neutral TurboTears domain; issue certificates and update DNS, `PUBLIC_WEB_URL`, `WEB_ORIGINS`, Telegram settings and email links together.
- Rename public social handles and store listings that use F1 / Formula 1 / Formula One as the product brand.
- Revoke or rotate old branded cookies during deployment and expect existing web sessions to require a new login.

## Rights and release controls

- Keep the service free, ad-free and non-commercial unless separate data and brand rights are obtained.
- Obtain written guidance or a license before substantial commercial use of results, timing, statistics or telemetry. Formula 1 directs licensing questions to `brandprotection@f1.com`.
- Complete the separate asset audit described in `ASSET_LICENSES.md`; this code change deliberately did not modify photographs, logos or circuit materials.
- Review whether `app-assets.zip` may legally remain in a public repository after the asset audit.
- Generate a complete dependency-license report for every public container release.
- Recheck Formula 1, OpenF1, Telegram and applicable privacy terms before material feature or monetization changes.

