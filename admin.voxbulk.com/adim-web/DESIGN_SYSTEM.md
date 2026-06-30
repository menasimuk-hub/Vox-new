# VoxBulk Admin — Design System

Source of truth for all visual design in `adim-web`.
Reference implementation: `telynx-settings-hub-main` (the approved dark Stripe-like style).

**Rule: no page may introduce a new color, spacing value, radius, shadow, or component variant that isn't defined here. If something is missing, add it here first, then use it.**

## 1. How tokens were derived
Cursor: before writing any code, open `telynx-settings-hub-main` and extract the actual values in use (Tailwind config, CSS variables, or inline classes) for colors, spacing, radius, fonts, shadows. Fill in section 2 below with the REAL values found — do not invent new ones.

## 2. Tokens

Extracted from the reference `telynx-settings-hub-main/src/styles.css` (`:root` = warm light theme, which matches the screenshots and the admin app). The `.dark` overrides exist in the reference and are carried into our `design-system.css` but light is the canonical set.

> Note on the section heading "dark Stripe-like": the reference's *default* (and the values below) is the warm **light** theme. The dark palette is an optional `.dark` override, not the primary look.

### Colors (exact `oklch` from reference)
- `--bg-base` (page background) = `--background`: `oklch(0.975 0.012 85)`
- `--bg-surface` (card/panel background) = `--card` / `--surface`: `oklch(0.995 0.004 85)`
- `--bg-surface-muted` = `--surface-muted` / `--muted`: `oklch(0.955 0.014 85)` / `oklch(0.945 0.014 80)`
- `--bg-surface-hover` (button/row hover) = `--secondary` / `--accent`: `oklch(0.93 0.012 80)`
- `--border-default` = `--border` / `--input`: `oklch(0.9 0.012 85)`
- `--border-subtle`: **derived, not a named token** → `color-mix(in oklch, var(--border) 60%, transparent)` (used for table row borders in the existing port)
- `--text-primary` = `--foreground`: `oklch(0.22 0.02 260)`
- `--text-secondary`: **no discrete token in reference** → aliased to `--muted-foreground`: `oklch(0.5 0.02 260)`
- `--text-muted` = `--muted-foreground`: `oklch(0.5 0.02 260)`
- `--accent` (brand ACTION color) = `--primary`: `oklch(0.27 0.04 265)` (deep navy); foreground `--primary-foreground`: `oklch(0.98 0.003 247)`
  - Caveat: shadcn's own `--accent` var is the light grey hover (`oklch(0.93 0.012 80)`); the real brand/action color is `--primary`.
- `--accent-hover` = primary at 90% opacity (reference uses the `hover:bg-primary/90` utility, not a separate token)
- `--ring` (focus): `oklch(0.62 0.05 260)`
- `--success`: `oklch(0.55 0.14 150)` · `--success-soft`: `oklch(0.93 0.06 150)`
- `--warning`: `oklch(0.62 0.13 65)` · `--warning-soft`: `oklch(0.93 0.05 75)`
- `--danger` / `--destructive`: `oklch(0.6 0.21 27)` · soft (port): `oklch(0.95 0.04 27)`
- `--info`: `oklch(0.52 0.1 250)` · `--info-soft`: `oklch(0.93 0.03 250)`

### Typography
- Font family: **no custom/brand font in the reference** — it uses the Tailwind default sans stack (`ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, ...`). Body sets `font-feature-settings: "cv02","cv03","cv04","cv11"`.
- Scale (from the actual component classes):
  - heading-lg: `text-lg` (1.125rem) `font-semibold` — dialog title
  - heading-md / card title: `font-semibold leading-none tracking-tight` (≈ `text-base`)
  - body: `text-sm` (0.875rem) — buttons, inputs, select, table cells
  - caption: `text-xs` (0.75rem) — badges, `sm` button, table header
  - weights: `font-medium` (500) buttons/labels, `font-semibold` (600) badges/headings

### Spacing & radius
- Radius base `--radius: 0.625rem` (10px). Derived steps: `sm` = radius−4px (6px), `md` = radius−2px (8px), `lg` = radius (10px), `xl` = radius+4px (14px), `2xl` = radius+8px (18px).
  - controls (button / input / select / badge): `rounded-md` (8px)
  - cards: `rounded-xl` (14px)
  - dialog: `sm:rounded-lg` (10px)
  - pills/badges-as-pill: `rounded-full`
- Spacing (Tailwind 4px scale, as actually used):
  - button: `h-9 px-4 py-2` · sm `h-8 px-3` · lg `h-10 px-8` · icon `h-9 w-9`
  - input / select trigger: `h-9 px-3 py-1` (`py-2` for select)
  - card: `p-6`; card header `space-y-1.5 p-6`
  - dialog: `p-6 gap-4`
  - table: header `h-10 px-2`, cell `p-2`
  - badge: `px-2.5 py-0.5`

### Shadows (Tailwind utility → computed value)
- Card / default button: `shadow` = `0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)`
- Outline / secondary / destructive button, input, select trigger: `shadow-sm` = `0 1px 2px 0 rgb(0 0 0 / 0.05)`
- Dialog content: `shadow-lg` = `0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)`
- Select dropdown content: `shadow-md` = `0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)`
- (The CSS port also uses a heavier custom modal shadow `0 24px 60px rgba(0,0,0,0.25)` — kept only as an alternative, not the shadcn default.)

## 3. Components (structure + classes copied from reference)

### Table (`Table.tsx`)
- Wrapper: `relative w-full overflow-auto`; table: `w-full caption-bottom text-sm`
- Header: `<thead>` `[&_tr]:border-b`; head cell `h-10 px-2 text-left align-middle font-medium text-muted-foreground`
- Row: `border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted`; body `[&_tr:last-child]:border-0`
- Cell: `p-2 align-middle`
- Footer: `border-t bg-muted/50 font-medium`
- Empty / loading states: provided via a thin `DataTable` helper (centered `text-muted-foreground` row spanning all columns); pagination row uses `Button variant="outline" size="sm"` controls + `text-xs text-muted-foreground` counter.

### Buttons (`Button.tsx`) — `cva` base
`inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 disabled:cursor-not-allowed [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0`
- Variants:
  - `default` (primary): `bg-primary text-primary-foreground shadow hover:bg-primary/90`
  - `secondary`: `bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80`
  - `outline`: `border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground`
  - `ghost`: `hover:bg-accent hover:text-accent-foreground`
  - `destructive`: `bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90`
  - `link`: `text-primary underline-offset-4 hover:underline`
- Sizes: `default h-9 px-4 py-2` · `sm h-8 rounded-md px-3 text-xs` · `lg h-10 rounded-md px-8` · `icon h-9 w-9`
- Disabled: `disabled:pointer-events-none disabled:opacity-50` (in base)

### Popups / Modals / Dialogs (`Modal.tsx`, from `dialog.tsx`)
- Overlay: `fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0`
- Content: `fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 ... data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 sm:rounded-lg`
- Header: `flex flex-col space-y-1.5 text-center sm:text-left`; Footer: `flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2`
- Title: `text-lg font-semibold leading-none tracking-tight`; Description: `text-sm text-muted-foreground`
- Close button (top-right): `absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100 transition-opacity` with an `<X className="h-4 w-4" />`

### Forms / Inputs (`Input.tsx`, `Select.tsx`, `Label.tsx`, `Textarea.tsx`)
- Input: `flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm`
  - Error state (added): `aria-invalid:border-destructive aria-invalid:focus-visible:ring-destructive`
- Label: `text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70`
- Select trigger: `flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm data-[placeholder]:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50` + `<ChevronDown className="h-4 w-4 opacity-50" />`
- Select content: `z-50 max-h-... min-w-[8rem] overflow-y-auto rounded-md border bg-popover text-popover-foreground shadow-md` (animated); item: `relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-2 pr-8 text-sm focus:bg-accent focus:text-accent-foreground` with a right-aligned `<Check className="h-4 w-4" />` indicator.

### Cards / Panels (`Card.tsx`)
- Card: `rounded-xl border bg-card text-card-foreground shadow`
- Header: `flex flex-col space-y-1.5 p-6`; Title: `font-semibold leading-none tracking-tight`; Description: `text-sm text-muted-foreground`
- Content: `p-6 pt-0`; Footer: `flex items-center p-6 pt-0`

### Badges / Status pills (`Badge.tsx`)
- Base: `inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors`
- Reference variants: `default` (primary), `secondary`, `destructive`, `outline`
- Status mapping (added, soft tones from the soft tokens above):
  - `active` → `border-transparent bg-success-soft text-success`
  - `inactive` → `border-transparent bg-surface-muted text-muted-foreground`
  - `pending` → `border-transparent bg-warning-soft text-warning`
  - `error` → `border-transparent bg-destructive/10 text-destructive`

## 4. Implementation rule for Cursor
When asked to "apply design system to page X":
1. Read this file fully.
2. Read the target page's current code.
3. Replace one-off styling (hardcoded hex, inline px values, ad-hoc button/table markup) with the shared components/tokens defined here.
4. Do NOT change page logic, data fetching, or routes — visual/structural only.
5. Do NOT introduce new tokens. If the page needs something not covered, stop and flag it instead of inventing a value.
6. Output a summary of every file changed and what was swapped (old → new).

## 5. Shared components checklist (build once, reuse everywhere)
- [ ] `<Button />` (all variants)
- [ ] `<Table />` (with pagination, empty/loading states)
- [ ] `<Modal />` / `<Dialog />`
- [ ] `<Input />`, `<Select />`
- [ ] `<Card />`
- [ ] `<Badge />`

Once these exist in `/src/components/ui/`, every page should import from there — not redefine its own table/button/modal markup.
