# Asset licensing register

This register documents provenance and license status. A file is not cleared for production merely because it exists in the repository or in `app-assets.zip`.

## Fonts loaded by the frontend

- Inter — Google Fonts / upstream project — SIL Open Font License 1.1.
- Space Grotesk — Google Fonts / upstream project — SIL Open Font License 1.1.

The frontend currently requests these fonts from Google Fonts. This external request must be reflected in the Privacy Policy or replaced with properly licensed self-hosted files in a later asset change.

## Flags

Status: provenance and license not verified in this change. Files are served from `app/assets/country` after unpacking `app-assets.zip`. Do not assume an open license until source, author, version and license are recorded for each set.

## Driver photographs

Status: intentionally not audited or modified in this change at the user's request. No license is asserted here. Production/public distribution requires a per-file source and license or removal.

## Team and organisation logos

Status: intentionally not audited or modified in this change at the user's request. Official logos and confusingly similar marks require permission from the respective right holders.

## Circuit illustrations and outlines

Status: intentionally not audited or modified in this change at the user's request. Existing SVG files and archived circuit materials remain pending a separate provenance and circuit-IP review.

## Application screenshots and other graphics

Status: pending. Screenshots may reproduce underlying photographs, logos, circuit graphics or protected interface elements and therefore require a derivative-material review.

## Admission rule

For every new visual or font asset, record before release:

1. repository path;
2. title and author/right holder;
3. original source URL or acquisition record;
4. exact license or written permission;
5. allowed media, territory, term and commercial-use status;
6. required attribution and proof-of-license location.

If these fields cannot be completed, the asset must not enter production.

