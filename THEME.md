# Dharani Coast

A custom theme built for DHARANI 360, derived directly from the DR logo rather
than from a stock palette. Sampling the logo file gives `#138198` for the teal
half and `#624B3C` for the copper half; those round to the brand tokens below.
Cool teal carries structure and action, warm copper carries emphasis and
identity. The layout, spacing and component anatomy follow the SmartHR admin
pattern — the colour is what makes it ours.

## Colour Palette

### Brand
- **Signal Teal**: `#0e7490` - primary action, links, active navigation, focus rings
- **Deep Teal**: `#0b5c73` - hover state for primary actions, text on a teal tint
- **Teal Tint**: `#e7f1f4` - active nav background, soft badges, welcome banner wash
- **Copper**: `#6b4226` - avatars, hero gradient anchor, secondary emphasis
- **Light Copper**: `#8a5a34` - copper hover
- **Copper Tint**: `#f2ece7`

### Surfaces
- **Page**: `#f6f8f9` - the application background
- **Card**: `#ffffff` with a `#e2eaec` hairline, 5px radius, 1px shadow
- **Hairline**: `#e2eaec` / `#e7eef0` (table heads) / `#f1f5f6` (fills)

### Text
- **Ink**: `#17202e` - headings and primary text
- **Slate**: `#6d7889` - body text, labels, meta
- **Slate Light**: `#9aa5b1` - captions and disabled states

### Status
- **Green** `#15803d` - **Amber** `#b45309` - **Red** `#b91c1c` - **Blue** `#1d6fa5`

Each is muted a notch from the usual neon so it sits with the teal and copper
without losing its meaning at a glance. Every pairing clears WCAG AA for
body-size text: white on teal 5.36:1, on copper 8.63:1, on green 5.02:1, on
amber 5.02:1, on red 6.47:1, on blue 5.43:1; Slate on the page background
4.59:1; Ink on white 17.7:1.

### Departments
The sixteen department accents are drawn from the same teal-to-copper arc
rather than a rainbow, so a dashboard full of department cards still reads as
one system. All sixteen clear 3:1 against white, the threshold for the icons
and left rails they colour.

Corporate `#0e7490` - People & HR `#2b6c86` - Agents `#3f8f9e` - Sales `#1d7a6c`
Properties `#4a8b6a` - Transactions `#8a6a2f` - Finance `#a35a34` - Compliance `#96412f`
IT & Assets `#3c5f80` - Vendors `#6d4d8f` - Payroll `#157b78` - Recruitment `#a8437a`
Attendance `#b06a2c` - Help Desk `#2f7fa5` - Projects `#4a6b8a` - Content `#6b4226`

## Typography

- **Family**: Roboto, self-hosted from `static/fonts/` at 300/400/500/600/700
- **Body**: 14px / 1.5, Slate
- **Headings**: 600-700, Ink, tightened tracking (`-0.3px`) at large sizes
- **Labels & eyebrows**: 600, uppercase, `+0.5px` tracking, 10-11px
- Nothing is fetched from a font CDN at runtime; the app stays fully offline

## Layout

- 252px white sidebar, sticky, with an orange-free teal rail on the active item
- 52px white top bar carrying search, quick actions, the date and the user chip
- 24px page gutter, 16px grid gap, cards that never nest more than one level
- The Rules & Regulations hero runs teal to copper left-to-right, mirroring the
  logo itself

## Best Used For

Operational and compliance systems where people read dense tables all day: the
brand is carried by the accents and the chrome, while every surface holding
real data stays high-contrast and quiet.
