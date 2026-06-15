# Apple Design System — Quick Reference

Source: `VoltAgent/awesome-design-md/design-md/apple` (Apache-2.0)

## Core Philosophy

- **Photography-first / Data-first**: UI recedes so content speaks
- **Alternating tiles**: White/parchment ↔ near-black, color change IS the divider
- **Single accent**: Action Blue (#0066cc) for ALL interactive elements
- **No decorative gradients, no shadows on chrome** — shadow reserved for product imagery only

## Key Tokens

| Token | Value | Use |
|-------|-------|-----|
| `--primary` | `#0066cc` | All links, CTAs, focus rings |
| `--primary-focus` | `#0071e3` | Keyboard focus ring |
| `--primary-on-dark` | `#2997ff` | Links on dark surfaces |
| `--ink` | `#1d1d1f` | Headlines, body text (NOT pure black) |
| `--canvas` | `#ffffff` | Primary light surface |
| `--canvas-parchment` | `#f5f5f7` | Alternating light surface |
| `--surface-tile-1` | `#272729` | Primary dark surface |
| `--surface-black` | `#000000` | Global nav, true void |

## Typography Rules

- **Font stack**: `Inter, SF Pro Display, system-ui, -apple-system, sans-serif`
- **Body**: 17px (not 16px), weight 400, line-height 1.47, letter-spacing -0.374px
- **Headlines**: weight 600 (not 700), negative letter-spacing at display sizes
- **Weight 300**: Reserved for large airy reads (button-large at 18px, lead-airy at 24px)
- **Weight 500**: Deliberately absent — ladder is 300/400/600/700

## Spacing

- Base unit: 8px
- Section padding: 80px (edge-to-edge tiles with 0 gap)
- Card padding: 24px
- Button padding: 11px × 22px

## Border Radius

| Token | Value | Use |
|-------|-------|-----|
| `--rounded-none` | `0px` | Full-bleed tiles |
| `--rounded-sm` | `8px` | Utility buttons |
| `--rounded-lg` | `18px` | Cards |
| `--rounded-pill` | `9999px` | Primary CTAs, search input |

## Button Grammar

```css
/* Primary — the signature Apple pill */
.btn-primary {
  background: var(--primary);
  color: white;
  padding: 11px 22px;
  border-radius: 9999px;  /* full pill */
  font-size: 17px;
  font-weight: 400;
  letter-spacing: -0.374px;
  border: none;
  transition: all 0.2s;
}
.btn-primary:active { transform: scale(0.95); }

/* Secondary — ghost pill */
.btn-secondary {
  background: transparent;
  color: var(--primary);
  border: 1px solid var(--primary);
  border-radius: 9999px;
  padding: 11px 22px;
}
```

## Component Patterns

### Frosted Glass Nav
```css
.sub-nav {
  background: rgba(245, 247, 247, 0.8);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  height: 52px;
}
```

### Content Tile (alternating)
```css
.tile-light { background: var(--canvas); }
.tile-parchment { background: var(--canvas-parchment); }
.tile-dark { background: var(--surface-tile-1); color: var(--on-dark); }
```

### Utility Card
```css
.card {
  background: var(--canvas);
  border-radius: 18px;
  padding: 24px;
  border: 1px solid var(--hairline);
}
```

## Responsive Breakpoints

| Name | Width | Key Changes |
|------|-------|-------------|
| Small phone | ≤419px | Single column, hero h1 → 28px |
| Phone | 420–640px | Single column, h1 → 34px |
| Tablet | 736–833px | Nav collapses to hamburger |
| Small desktop | 1024–1068px | 2/3 width tiles |
| Desktop | 1069–1440px | Full layout, 4-5 col grids |
| Wide | ≥1441px | Content locks at 1440px |

## Do's

- Use `{colors.primary}` for every interactive element
- Negative letter-spacing on headlines (-0.12 to -0.374px)
- Body at 17px, not 16px
- Alternate light/dark tiles for section rhythm
- `transform: scale(0.95)` as active/press state on all buttons

## Don'ts

- No second accent color
- No shadows on cards/buttons/text (only on product imagery)
- No decorative gradients
- No weight 500 (use 400 or 600)
- Don't round full-bleed tiles
- Don't tighten body line-height below 1.47
