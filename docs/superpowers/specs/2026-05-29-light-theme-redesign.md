# Light Theme UI Redesign

## Summary

Rewrite the PM Agent frontend from dark theme to a light, modern-minimal design. Pure CSS rewrite — no new dependencies, minimal HTML changes.

## Color System

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#f8f9fa` | Page background |
| `--surface` | `#ffffff` | Cards, panels |
| `--surface-hover` | `#eff6ff` | Row hover, selected |
| `--primary` | `#2563eb` | Buttons, links, accent |
| `--primary-light` | `#dbeafe` | Primary bg tint |
| `--success` | `#16a34a` | Done status, progress fill |
| `--warning` | `#d97706` | Warning/overdue |
| `--danger` | `#dc2626` | Blocked, delete, overdue fill |
| `--text` | `#1e293b` | Primary text |
| `--text-secondary` | `#64748b` | Secondary text, hints |
| `--border` | `#e2e8f0` | Borders, dividers |
| `--border-light` | `#f1f5f9` | Subtle borders |

## Typography & Spacing

- Font stack unchanged: system fonts + PingFang SC + Microsoft YaHei
- Base unit: 8px (4/8/12/16/24px scale)
- Border radius: cards 12px, buttons/inputs 8px, badges 999px
- Shadows: light `0 1px 3px rgba(0,0,0,0.06)` on cards, slightly heavier on drawer

## Layout (unchanged DOM structure)

- Body: white → tinted `#f8f9fa` bg
- Header: white card, thin bottom border
- Main panel: white card + light shadow
- Chat panel: `#f1f5f9` bg, white message bubbles
- Detail drawer: white bg, left shadow

## Task Rows

- White bg, light blue `#eff6ff` on hover
- Done rows: reduced opacity + strikethrough
- Progress bar: `#e2e8f0` track, green→blue gradient fill
- Time track: green (upcoming), amber (warning), red (overdue), green (done)
- Tree indent: left border `#e2e8f0`

## Interactive States

- Buttons: clear hover/active states with color shifts
- Badges: light tinted backgrounds with saturation instead of heavy borders
- Inputs: white bg, light border, blue focus ring
- Toasts: light tinted bg with semantic colors

## Mobile

- Full-width drawer below 900px
- Grid columns reduce (same breakpoint behavior, adjusted colors)

## Scope

- `static/css/app.css` — full rewrite (~1100 lines → ~900 lines)
- No JS changes (all class names and selectors preserved)
- No HTML template changes needed
