# Interface design

For interface changes, apply [Apple Design Skill](https://github.com/dickwu/apple-design-skill)
and use WCAG 2.2 AA as the accessibility target. Read the skill and relevant HIG
references before making a new design decision; translate their principles to
React and the web. Preserve TurboTears branding and existing product behavior.
Use the installed `apple-design` skill at `$CODEX_HOME/skills/apple-design/SKILL.md`
(normally `~/.codex/skills/apple-design/SKILL.md`). Route topics with its
`references/hig-lookup.md` and read the relevant HIG files before reviewing.

- Reuse `src/assets/design-system.css` for shared colors, navigation and controls.
  Use semantic `--design-*` tokens for both themes.
- Ground interface changes in a specific Apple Design Skill/HIG guideline or an
  explicit user requirement. Do not add actions, navigation or decoration solely
  to make a screen look more Apple-like. Preserve existing behavior where the
  guidelines do not require a change; identify web implementation parameters as
  implementation choices, never as Apple requirements.
- Keep a visible theme button. The user's explicit preference for a manual
  light/dark switch takes precedence over HIG advice to avoid app-specific theme
  settings. Store the choice; follow the system until the user chooses.
- Use one responsive markup tree per screen. Reveal secondary details on request;
  never delay essential data until an animation finishes.
- Check contrast, native keyboard access, visible focus, meaningful labels,
  heading order, text scaling and narrow-screen reflow. Prefer 44px control targets;
  do not disable browser zoom or rely only on color or motion.
- Test changed flows and failure states. Keep fake preview data separate from
  production entry points. Do not claim full WCAG conformance from automated
  checks or screenshots alone.
- Migrate older content route by route. Preserve readable legacy surfaces until
  that route is redesigned; do not assume every existing screen has been audited.

The current design and preview workflow are described in `../docs/home-design.md`
and `../docs/weekend-design.md`.
The complete home-screen review and current installation status are in
`../docs/home-design-review.md`.
