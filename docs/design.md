# Komponist Design System

> Design specification for a developer-first company-context platform. This document translates the reference website into a reusable visual, interaction, and content system under the **Komponist** brand.

## 1. Purpose

Use this system for two related surfaces:

1. **Marketing website** — editorial, confident, playful, and code-forward.
2. **Komponist Studio** — compact, data-dense, operational, and calm.

Both surfaces must feel like the same product:

- technical without becoming sterile;
- expressive without becoming decorative;
- highly structured without looking corporate;
- playful in copy, restrained in UI;
- credible enough for infrastructure and permissions work.

## 2. Brand rules

### 2.1 Product name

The product name is always **Komponist**.

Use:

- `Komponist`
- `Komponist Studio`
- `Komponist API`
- `Komponist SDK`
- `Komponist context compiler`
- `@komponist/sdk`
- `api.komponist.build`
- `mcp.komponist.build`
- `KOMPONIST_API_KEY`

Do not use alternate product names, legacy names, abbreviations, or a generic placeholder brand.

### 2.2 Brand idea

Komponist turns scattered company knowledge into governed context that humans and AI agents can use.

The name suggests composition rather than storage: Komponist assembles sources, identities, permissions, evidence, and relationships into a coherent result.

### 2.3 Suggested descriptor

**The programmable company brain.**

Alternative supporting line:

**Company context, composed for every agent.**

### 2.4 Logo treatment

Use a text-first wordmark:

- wordmark: `Komponist`;
- sentence case, not all caps;
- medium or semibold weight;
- no gradient fill;
- no glossy symbol;
- no generic brain icon.

An optional compact mark may be built from a monospaced `K`, a brace-like form, or intersecting lines that suggest orchestration. It must remain geometric and legible at 16 px.

## 3. Design principles

### 3.1 Editorial hierarchy

Large, concise headlines should lead each section. Supporting copy stays narrow and readable. Let scale, spacing, and rules create hierarchy instead of decorative illustration.

### 3.2 Infrastructure made tangible

Represent abstract system behavior with concrete artifacts:

- code snippets;
- numbered flows;
- structured context packs;
- source labels;
- permission traces;
- compact diagrams;
- operational tables;
- metrics and logs.

### 3.3 Monochrome first, accent second

Most of the interface is warm neutral, black, white, and gray. Accent color is used deliberately for selection, emphasis, progress, and primary actions—not as a background wash across every section.

### 3.4 Flat and bordered

Prefer one-pixel rules, blocks, and clear alignment over heavy shadows. Surfaces should feel printed, engineered, and stable.

### 3.5 Playful copy, serious controls

Humor belongs in headlines, annotations, empty states, and supporting lines. Permissions, errors, destructive actions, and system status must remain direct and unambiguous.

### 3.6 Visible provenance

Whenever the product presents an answer or fact, the design should make evidence, freshness, identity, confidence, and permission state easy to inspect.

## 4. Visual character

Use these keywords when evaluating new work:

- editorial developer tool;
- warm monochrome;
- oversized typography;
- terminal precision;
- thin rules;
- compact data UI;
- symbolic micro-illustration;
- dry humor;
- calm infrastructure;
- high information density.

Avoid:

- glassmorphism;
- neon gradients;
- floating 3D blobs;
- cartoon brains;
- excessive pill shapes;
- large soft shadows;
- generic AI sparkle imagery;
- purple-on-black “AI product” styling;
- stock photography.

## 5. Design tokens

The values below are implementation tokens calibrated to the visual character of the reference. Keep the relationships between tokens even when adjusting individual values after a browser-side visual comparison.

### 5.1 Color

```css
:root {
  /* Canvas and surfaces */
  --color-paper: #fdf9f1;
  --color-paper-2: #f6eedf;
  --color-paper-3: #efe5d2;
  --color-white: #fffdf8;

  /* Text */
  --color-ink: #201c15;
  --color-ink-2: #4a443a;
  --color-muted: #6b6257;
  --color-faint: #9a9184;

  /* Lines */
  --color-line: #d9cfbf;

  /* Brand accent */
  --color-orange: #e8641b;
  --color-orange-dark: #c2500d;
  --color-peach: #f5a46b;

  /* Secondary accent */
  --color-teal: #0e8a7d;
  --color-teal-light: #7bc4b9;

  /* Semantic */
  --color-success: #0e8a7d;
  --color-success-soft: #e0f2ef;
  --color-warning: #e8641b;
  --color-warning-soft: #fef0e8;
  --color-danger: #c2500d;
  --color-danger-soft: #fce8e0;
  --color-info: #365fbd;
  --color-info-soft: #dfe7f7;

  /* Code */
  --color-code-bg: #201c15;
  --color-code-surface: #2a2520;
  --color-code-text: #fdf9f1;
  --color-code-muted: #9a9184;
  --color-code-keyword: #e8641b;
  --color-code-string: #f5a46b;
  --color-code-number: #7bc4b9;
  --color-code-comment: #6b6257;

  /* Focus */
  --color-focus: #0e8a7d;
}
```

### 5.2 Color usage

| Token | Use |
|---|---|
| Paper | Main marketing background and quiet Studio backgrounds |
| Paper-2 | Cards, tables, nav, secondary surfaces |
| Paper-3 | Subtle backgrounds, hover states |
| White | Elevated surfaces, inputs |
| Ink | Primary text, borders on high-emphasis controls |
| Orange | Primary CTA, selected tabs, active markers, small highlights |
| Teal | Secondary accent, success states, links |
| Inverse (Ink) | Code panels, selected navigation, final CTA blocks |
| Semantic colors | Status only; never use them as arbitrary decoration |

Rules:

- Maintain at least 4.5:1 contrast for body text.
- Never use accent-colored body text on the canvas.
- Do not communicate status through color alone; pair it with text, an icon, or a pattern.
- Use white rather than the canvas color inside dense data tables to preserve clarity.

### 5.3 Typography

Use open or system-safe families.

```css
:root {
  --font-display: "Bricolage Grotesque", "Arial Rounded MT Bold", "Avenir Next", sans-serif;
  --font-body: "Instrument Sans", "Avenir Next", Avenir, sans-serif;
  --font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
}
```

Recommended loading:

- Display: Bricolage Grotesque, 600–700.
- Body/UI: Instrument Sans, 400–600.
- Code/data: JetBrains Mono, 400–600.

Do not use a serif display font. The personality should come from scale, line breaks, and language rather than an ornamental typeface.

### 5.4 Type scale

```css
:root {
  --text-hero: clamp(4rem, 8vw, 7.5rem);
  --text-display: clamp(3rem, 5.5vw, 5.5rem);
  --text-h1: clamp(2.75rem, 4.5vw, 4.5rem);
  --text-h2: clamp(2rem, 3vw, 3.25rem);
  --text-h3: clamp(1.35rem, 2vw, 1.75rem);
  --text-lead: clamp(1.125rem, 1.7vw, 1.35rem);
  --text-body: 1rem;
  --text-small: 0.875rem;
  --text-caption: 0.75rem;
  --text-micro: 0.6875rem;
}
```

Typography behavior:

- Hero: display family, 650–700 weight, `0.9–0.96` line-height, tight tracking.
- Section headline: display family, 600–700, `0.98–1.08` line-height.
- Body: 400–450, `1.5–1.65` line-height.
- Labels: 500–600, often uppercase or compact sentence case.
- Code and metrics: mono family with tabular numerals.
- Keep marketing paragraphs between 48 and 68 characters per line.

### 5.5 Spacing

Use a 4 px base unit.

```css
:root {
  --space-0: 0;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --space-12: 3rem;
  --space-16: 4rem;
  --space-20: 5rem;
  --space-24: 6rem;
  --space-32: 8rem;
  --space-40: 10rem;
}
```

Marketing section rhythm:

- desktop section padding: `96–160 px`;
- tablet section padding: `72–112 px`;
- mobile section padding: `56–80 px`;
- major heading to supporting paragraph: `20–32 px`;
- section intro to component grid: `40–64 px`.

Studio rhythm:

- page padding: `24–32 px`;
- card padding: `16–24 px`;
- row height: `44–52 px`;
- dense controls: `32–36 px` high.

### 5.6 Layout

```css
:root {
  --container-max: 1280px;
  --container-reading: 760px;
  --gutter-mobile: 20px;
  --gutter-tablet: 32px;
  --gutter-desktop: 48px;
}
```

Desktop marketing grid:

- 12 columns;
- 24 px column gap;
- asymmetrical section layouts are encouraged;
- hero text usually occupies 7–8 columns;
- code or artifact panel occupies 4–5 columns;
- full-width rules align to the same container.

Studio shell:

- top bar: 48–56 px;
- side navigation: 224–248 px;
- content area: fluid;
- optional right inspector: 320–400 px;
- minimum useful app viewport: 1024 px.

### 5.7 Borders and radius

```css
:root {
  --border-width: 1px;
  --radius-none: 0;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-pill: 999px;
}
```

Rules:

- Default cards: 8 px radius or square corners.
- Code panels: 8–12 px radius.
- Buttons: 4–6 px radius.
- Pills are reserved for status, filters, and compact metadata.
- A section can intentionally use square corners to feel more editorial.

### 5.8 Shadows

```css
:root {
  --shadow-none: none;
  --shadow-subtle: 0 1px 2px rgb(17 18 15 / 0.06);
  --shadow-popover: 0 12px 32px rgb(17 18 15 / 0.14);
}
```

Use borders before shadows. Only menus, popovers, and temporary overlays need a pronounced shadow.

### 5.9 Motion

```css
:root {
  --duration-fast: 120ms;
  --duration-base: 180ms;
  --duration-slow: 320ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --ease-enter: cubic-bezier(0, 0, 0.2, 1);
}
```

Motion rules:

- Buttons and links: color or position transition within 120–180 ms.
- Cards: no floating hover animation; use border or background change.
- Tabs: underline or background moves, content crossfades lightly.
- Live logs: new rows may fade and slide 4 px upward.
- Diagrams: reveal connections progressively, not continuously.
- Respect `prefers-reduced-motion`.

## 6. Iconography and symbols

Use simple line icons or typographic symbols. Stroke width should be 1.5–1.75 px.

Preferred visual vocabulary:

- arrows: `→`, `↗`, `↓`, `↶`;
- braces: `{ }`;
- checks: `✓`;
- cross/denied: `×`;
- graph or node symbols;
- terminal prompt marks;
- compact source initials such as `SL`, `NO`, `GD`, `CRM`.

Icons should feel annotated, not illustrated. A symbol may sit beside a section number or category name, but it should not overpower the label.

## 7. Marketing website anatomy

### 7.1 Announcement bar

Purpose: communicate beta access, a launch note, or a concise claim.

Specification:

- height: auto, minimum 36 px;
- background: accent or inverse;
- one short sentence and one text link;
- 12–14 px text;
- centered on mobile, horizontally aligned with the site container on desktop;
- link ends with `→`.

Example:

> Design partner beta is open. Give your company context object permanence. Talk to us →

### 7.2 Header

Desktop structure:

- left: Komponist wordmark;
- center or left-adjacent: Product, Developers, Beta, Studio;
- right: Contact and primary CTA;
- 64–76 px height;
- one-pixel bottom border;
- canvas or slightly translucent canvas background;
- sticky only when it does not obscure the announcement bar.

Navigation behavior:

- current page is indicated by weight, underline, or a small accent marker;
- “Studio” may carry a small `Beta` label;
- primary CTA is compact, not oversized;
- hover uses underline offset or a 1–2 px arrow shift.

Mobile:

- wordmark left;
- menu trigger right;
- full-height or large sheet menu;
- retain Contact and primary CTA as separate actions.

### 7.3 Hero

The hero should combine an editorial statement with a functioning product artifact.

Structure:

1. small eyebrow;
2. two-line, oversized headline;
3. supporting paragraph;
4. primary and secondary actions;
5. code statement or annotation;
6. code panel or structured artifact.

Recommended Komponist hero copy pattern:

- Eyebrow: `The programmable company brain`
- Headline: `Stop asking Dave. Ask the brain.`
- Body: explain connectors, identity, permissions, context graph, and cited evidence in one paragraph.

Hero layout:

- desktop: 7/5 or 8/4 split;
- mobile: stack content first, artifact second;
- minimum desktop hero height: 720 px including header;
- code panel should appear grounded in the grid, not floating in space.

### 7.4 Code artifact

Use a dark panel with a narrow title bar.

Anatomy:

- filename on left;
- optional environment/status on right;
- syntax-highlighted code;
- output or annotation separated by a thin rule;
- mono font at 13–15 px;
- line height around 1.65;
- horizontal scroll on small screens;
- optional copy button appears on hover/focus.

Komponist example:

```ts
import { Komponist } from '@komponist/sdk'

const komponist = new Komponist(KOMPONIST_KEY)

const context = await komponist.context({
  user: 'priya@acme.com',
  task: 'Explain EU pricing'
})
```

Output annotations should be human and concise:

```txt
3 permitted facts · 2 citations
Context composed. Dave was at lunch. Nobody was harmed.
```

### 7.5 Comparison strip

Use a horizontal two-part statement to explain the category shift.

Example:

- `Databases make application data programmable`
- arrow or dividing rule;
- `Komponist makes company knowledge programmable`

Style:

- top and bottom borders;
- generous vertical padding;
- 20–32 px type;
- may stack on mobile;
- arrow remains visually prominent.

### 7.6 Feature grid

Use a six-item grid for the platform’s core capabilities.

Desktop:

- 3 columns × 2 rows, or 2 columns × 3 rows;
- one-pixel internal rules;
- no individual floating card shadows;
- each item receives a two-digit number and a symbol;
- title, short paragraph, and optional link.

Suggested capabilities:

1. Ingest everything
2. Compile context
3. Permissions built in
4. API and SDKs
5. Context analytics
6. Context graph

Feature item anatomy:

```txt
01 ↳
Ingest everything
Short explanatory paragraph.
See connectors →
```

Hover:

- background shifts to surface;
- arrow moves 2 px;
- border remains stable so the grid does not jump.

### 7.7 Developer section

Use an asymmetrical section with:

- large headline and concise benefit list on one side;
- interactive code panel on the other;
- language tabs such as `curl`, `typescript`, and `python`;
- copied code must use Komponist names and endpoints.

Benefit list:

- permission-aware retrieval by default;
- citations and freshness retained;
- shared context graph for every agent.

### 7.8 Three-step process

Use a numbered linear sequence:

1. Connect sources
2. Komponist organizes context
3. Build from anywhere

Desktop:

- three equal columns with top border;
- step number above heading;
- optional directional connector.

Mobile:

- vertical stack;
- connecting rule continues down the left edge;
- numbers remain aligned.

### 7.9 Beta CTA

The final CTA may switch to an inverse surface.

Anatomy:

- small label;
- large statement;
- concise explanatory paragraph;
- primary action and secondary text link;
- optional short technical annotation.

Keep this section blunt and conversion-focused. Do not add a multi-field form directly inside the CTA unless the product flow requires it.

### 7.10 Footer

Use a large, structured footer with one top rule.

Columns:

- brand and descriptor;
- Product;
- Developers;
- Company or Contact.

Bottom row:

- copyright;
- legal links;
- monospaced easter egg.

Example easter egg:

```sql
SELECT * FROM company_context;
```

## 8. Feature-detail page patterns

Feature pages should feel like deeper editorial documentation rather than a separate marketing template.

### 8.1 Diagram panel

Represent system flow with labeled blocks and arrows:

```txt
Sources
↓ revisions + identity + native access controls
Komponist
↓ cited Context Pack
Products and agents
```

Rules:

- text is the diagram;
- use boxes, rules, initials, and arrows;
- do not replace the diagram with a glossy illustration;
- retain readable order on mobile.

### 8.2 Mapping table

Use paired rows to explain category equivalence.

Example:

| Application data layer | Komponist context layer |
|---|---|
| Tables | Typed entities and facts |
| Auth users | Organizational identities |
| Row-level security | Source access controls and context policies |
| Queries | Context compiler |
| Migrations | Context schema versions |
| Recovery | Time-travel context |
| Logs | Evidence and authorization trail |

Visual treatment:

- no zebra striping by default;
- strong header rule;
- row dividers;
- arrow or “becomes” label can bridge columns;
- collapse to stacked pairs on narrow screens.

### 8.3 Use-case cards

Use department labels plus one symbolic mark:

- Support `☏`
- Sales `↗`
- Engineering `{ }`
- Product `✦`
- People `☺`
- Leadership `◎`

Each card contains:

- category label;
- benefit-led heading;
- two-sentence description;
- monospaced example question.

### 8.4 Interactive simulation

The simulation should expose the plumbing rather than mimic a chatbot.

Show:

- selected team;
- agent task;
- querying identity;
- compiler state;
- permitted facts;
- citations;
- excluded content with reason.

Do not show only a polished natural-language answer. The core value is the governed context pack.

### 8.5 Product boundaries

Use numbered statements for “Komponist is not…” content. This section should be visually direct and may use an inverse or high-contrast background.

## 9. Komponist Studio

The Studio is a separate density mode of the same design system.

### 9.1 Studio shell

Top bar:

- consistent page icon, section label, title, and optional description;
- page-scoped actions on the right;
- compact actions on mobile without repeating global navigation.

Left navigation groups:

- Brain: Chat, Workrooms, Canvas, Compose, Versions, Graph, Review Queue,
  Entities;
- Sources: Connected, Add Source;
- Settings: General, AI Provider, Team & departments, API & MCP, Export;
- Resources: GitHub.

Bottom sidebar area:

- appearance toggle;
- signed-in member, role, email, and explicit sign-out action.

### 9.2 Studio color mode

Use a light, neutral interface by default:

- white navigation and cards;
- warm-gray application background;
- dark text;
- accent for selected navigation and primary actions;
- semantic colors reserved for state.

Light and dark mode are both supported. Every product surface must use the
shared semantic color tokens rather than hard-coded light-only values.

### 9.3 Page header

Anatomy:

- title;
- last-updated timestamp;
- compact date-range tabs;
- right-aligned primary action.

Example:

```txt
Overview                         + Connect source
Last updated 2 min ago     24h  7d  30d
```

### 9.4 Metric cards

Display 4–6 compact cards in a responsive grid.

Card content:

- metric label;
- primary value;
- delta or qualifier;
- optional tooltip;
- optional concept/simulated label when data is illustrative.

Examples:

- Artifacts
- Context requests
- Pack acceptance
- Average compile time
- Mapped identities
- Permission denies

Rules:

- values use tabular numerals;
- do not use large decorative icons;
- delta is secondary, not visually louder than the value;
- place concept labels beside the metric, not hidden in a tooltip.

### 9.5 Charts

Chart style:

- thin axes and grid lines;
- no 3D effects;
- two series maximum before introducing filters;
- direct labels preferred over remote legends;
- tooltip uses mono numerals;
- denied/blocked series must differ by pattern or marker as well as color.

### 9.6 Knowledge-gap list

Rows contain:

- unresolved question;
- occurrence count;
- optional latest-seen timestamp;
- arrow or “View” action.

Emphasize the question, not the count.

### 9.7 Source health table

Recommended columns:

- Source
- Scope
- Artifacts
- 7-day change
- Last sync
- Cited in packs
- Status

Source identity may use two-letter abbreviations in a small square marker.

Status examples:

- Healthy
- Syncing
- Rate limited
- Paused
- Error

Each state requires:

- text label;
- icon or dot;
- accessible status announcement;
- optional animated ellipsis only for an active operation.

### 9.8 Recent context requests

Recommended columns:

- Task
- Identity
- Latency
- Confidence
- Via

Task is the dominant column. Identity should be easy to scan. Latency and confidence use monospaced numerals. Low confidence receives a semantic warning treatment but does not become a red error by default.

## 10. Components

### 10.1 Primary button

```css
.button-primary {
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid var(--color-ink);
  border-radius: var(--radius-sm);
  background: var(--color-accent);
  color: var(--color-on-accent);
  font-weight: 600;
}
```

States:

- hover: accent hover color, arrow shifts 2 px;
- active: accent pressed color;
- focus: 2 px focus ring with 2 px offset;
- disabled: 45% opacity, no arrow motion, `not-allowed` cursor.

### 10.2 Inverse button

- black/inverse background;
- light text;
- black border;
- hover may invert to accent when used on a light canvas.

### 10.3 Secondary button

- transparent background;
- one-pixel ink border;
- hover background becomes surface-subtle;
- never use a faint gray border that disappears on the canvas.

### 10.4 Text link

- visible underline or directional arrow;
- underline offset: 3–4 px;
- hover: underline thickens or arrow shifts;
- external links use `↗`.

### 10.5 Tabs

Marketing/code tabs:

- small mono text;
- active tab uses accent underline or accent fill;
- no pill container unless space is constrained.

Studio range tabs:

- compact segmented control;
- 32–36 px high;
- selected item uses inverse fill or strong border.

### 10.6 Badge

Use badges for:

- Beta;
- concept data;
- environment;
- permission result;
- freshness state.

Badge anatomy:

- 11–12 px text;
- 20–24 px height;
- border plus subtle fill;
- 999 px radius is acceptable because badges are metadata.

### 10.7 Card

Default card:

- surface background;
- one-pixel line;
- 8 px radius;
- no shadow;
- 20–24 px padding;
- heading separated from metadata by 8–12 px.

Interactive card:

- full card receives visible focus state;
- hover changes background or border color;
- do not translate or scale the whole card.

### 10.8 Code panel

Required features:

- language label;
- filename or endpoint;
- copy action;
- horizontal overflow;
- accessible syntax colors;
- selectable text;
- optional response pane.

### 10.9 Table

- sticky header for long tables;
- 44–52 px rows;
- 14 px body text;
- one-pixel row separators;
- no vertical borders unless they clarify paired columns;
- selected row uses accent-soft or surface-subtle;
- actions appear on row hover and keyboard focus.

### 10.10 Input

- 40 px default height;
- 1 px line-strong border;
- 4 px radius;
- 14–16 px text;
- clear label above;
- help and error text below;
- focus ring must not rely only on border color.

### 10.11 Command search

- contains search symbol and `⌘K` hint;
- medium width on desktop;
- becomes an icon button below tablet width;
- opens a centered command palette with grouped actions and recent destinations.

### 10.12 Toast

Use for transient confirmation only.

- bottom-right desktop, bottom-center mobile;
- surface or inverse background;
- one-line message where possible;
- optional undo action;
- automatically dismiss noncritical notices after 4–6 seconds;
- errors remain until dismissed or resolved.

### 10.13 Empty state

Empty states can use restrained humor, followed by a precise action.

Pattern:

1. direct heading;
2. one concise explanatory sentence;
3. one primary action;
4. optional docs link.

Do not use a large illustration.

## 11. Interaction states

### 11.1 Hover

Hover should reveal affordance without moving layout:

- arrow shifts 2 px;
- underline appears;
- background changes one neutral step;
- border strengthens;
- row actions fade in.

### 11.2 Focus

All interactive elements require a visible focus ring:

```css
:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}
```

Never remove outlines without a replacement.

### 11.3 Loading

Prefer content-shaped skeletons for cards and tables. Use a spinner only for a compact button or a blocking process.

For context compilation, expose meaningful stages when the wait exceeds roughly two seconds:

```txt
Resolving identity
Checking permissions
Gathering evidence
Composing Context Pack
```

### 11.4 Error

Errors must say:

- what failed;
- whether data may be incomplete;
- what the user can do next;
- whether the operation can be retried safely.

Permission denial is not a generic system error. Present it as an intentional result with an authorization explanation.

## 12. Responsive behavior

### 12.1 Breakpoints

```css
/* mobile first */
@media (min-width: 640px)  { /* sm */ }
@media (min-width: 768px)  { /* md */ }
@media (min-width: 1024px) { /* lg */ }
@media (min-width: 1280px) { /* xl */ }
@media (min-width: 1536px) { /* 2xl */ }
```

### 12.2 Marketing

Below 768 px:

- stack all split layouts;
- reduce hero to 64–72 px minimum type when space allows, otherwise use the fluid token;
- code panels span viewport width within the gutter;
- feature grid becomes one column;
- comparison pairs stack with a downward arrow;
- keep section numbers visible;
- footer columns become accordion groups only when link volume requires it.

Between 768 and 1024 px:

- use 6-column grid;
- two-column feature grid;
- hero may remain stacked if the code block would become too narrow.

### 12.3 Studio

Below 1024 px:

- side navigation collapses into a drawer;
- top bar retains organization, search trigger, and avatar;
- metric cards become two columns;
- wide tables use horizontal scroll or a mobile row-detail pattern;
- never hide permission state, source status, or identity merely to save width.

Below 640 px:

- metric cards become one column;
- page actions move below title;
- tables convert to labeled key-value rows when practical;
- command palette uses full-screen presentation.

## 13. Accessibility

Minimum requirements:

- WCAG 2.2 AA contrast;
- semantic headings in order;
- skip-to-content link;
- keyboard access for every control;
- focus-visible states;
- minimum 44 × 44 px touch target where possible;
- charts include text summaries or accessible tables;
- status is not conveyed only by color;
- code blocks have language labels;
- animated status honors reduced motion;
- tooltips are supplementary, never the sole carrier of required information;
- icon-only buttons have accessible names;
- tables identify headers and support logical reading order.

## 14. Voice and writing

### 14.1 Tone

Komponist sounds:

- concise;
- technically literate;
- self-aware;
- confident but not grandiose;
- dryly humorous;
- specific about system behavior.

### 14.2 Copy pattern

A strong section usually contains:

1. a small category label;
2. a short, memorable headline;
3. one paragraph explaining the actual mechanism;
4. a concrete artifact or example;
5. a direct action.

### 14.3 Humor rules

Good:

- “Dave can finally eat lunch.”
- “The wiki nobody updates.”
- “Your weird idea.”
- “A healthy distrust of uncited answers.”

Avoid humor in:

- security incidents;
- destructive confirmation dialogs;
- access denial explanations;
- billing failure;
- legal and privacy notices;
- data loss or sync failure.

### 14.4 Terminology

Prefer:

- context;
- evidence;
- source;
- citation;
- freshness;
- identity;
- permission;
- access control;
- context graph;
- Context Pack;
- compiler;
- trace;
- replay;
- gap;
- source health.

Avoid vague AI terms such as “magic,” “supercharge,” “revolutionary,” and “intelligent insights” unless followed by a concrete mechanism.

## 15. Brand replacement map

Use these Komponist-native examples consistently across marketing, documentation, and product UI.

| Surface | Komponist form |
|---|---|
| Wordmark | Komponist |
| Studio | Komponist Studio |
| SDK import | `import { createKomponistClient } from '@komponist/sdk'` |
| Client | `const komponist = createKomponistClient({ url, apiKey })` |
| API host | `https://api.komponist.build` |
| MCP host | `https://mcp.komponist.build/mcp` |
| Context call | `komponist.context.search(question, options)` |
| Brain call | `komponist.brain.info()` |
| Example filename | `ask-komponist.ts` |
| CLI proposal | `komponist context compile` |
| Environment label | `komponist / production` |
| Product statement | `Komponist makes company knowledge programmable` |

## 16. CSS starter

```css
* {
  box-sizing: border-box;
}

html {
  color-scheme: light;
  background: var(--color-paper);
  color: var(--color-ink);
  font-family: var(--font-body);
  text-rendering: optimizeLegibility;
}

body {
  margin: 0;
  background: var(--color-paper);
  color: var(--color-ink);
  font-size: var(--text-body);
  line-height: 1.6;
}

::selection {
  background: var(--color-orange);
  color: var(--color-white);
}

.container {
  width: min(
    calc(100% - (2 * var(--gutter-mobile))),
    var(--container-max)
  );
  margin-inline: auto;
}

.section {
  padding-block: var(--space-24);
  border-top: 1px solid var(--color-line);
}

.eyebrow {
  margin: 0 0 var(--space-4);
  color: var(--color-ink-2);
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.display {
  max-width: 12ch;
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--text-display);
  font-weight: 700;
  letter-spacing: -0.045em;
  line-height: 0.98;
}

.prose-lead {
  max-width: 62ch;
  color: var(--color-ink-2);
  font-size: var(--text-lead);
}

.rule-grid {
  display: grid;
  border-top: 1px solid var(--color-line);
  border-left: 1px solid var(--color-line);
}

.rule-grid > * {
  border-right: 1px solid var(--color-line);
  border-bottom: 1px solid var(--color-line);
}

@media (min-width: 768px) {
  .container {
    width: min(
      calc(100% - (2 * var(--gutter-tablet))),
      var(--container-max)
    );
  }

  .section {
    padding-block: var(--space-32);
  }
}

@media (min-width: 1280px) {
  .container {
    width: min(
      calc(100% - (2 * var(--gutter-desktop))),
      var(--container-max)
    );
  }
}
```

## 17. Tailwind token mapping

Suggested semantic names:

```js
// tailwind.config.js
export default {
  theme: {
    extend: {
      colors: {
        paper: '#fdf9f1',
        'paper-2': '#f6eedf',
        'paper-3': '#efe5d2',
        white: '#fffdf8',
        ink: '#201c15',
        'ink-2': '#4a443a',
        muted: '#6b6257',
        faint: '#9a9184',
        line: '#d9cfbf',
        orange: '#e8641b',
        'orange-dark': '#c2500d',
        peach: '#f5a46b',
        teal: '#0e8a7d',
        'teal-light': '#7bc4b9',
        success: '#0e8a7d',
        warning: '#e8641b',
        danger: '#c2500d',
        info: '#365fbd'
      },
      fontFamily: {
        display: ['Bricolage Grotesque', 'Arial Rounded MT Bold', 'Avenir Next', 'sans-serif'],
        body: ['Instrument Sans', 'Avenir Next', 'Avenir', 'sans-serif'],
        mono: ['JetBrains Mono', 'SFMono-Regular', 'Consolas', 'monospace']
      },
      maxWidth: {
        site: '1280px',
        reading: '760px'
      },
      borderRadius: {
        sm: '4px',
        md: '8px',
        lg: '12px'
      }
    }
  }
}
```

## 18. Page-level implementation checklist

### Marketing page

- [ ] Announcement bar is concise and actionable.
- [ ] Header uses the Komponist wordmark.
- [ ] Hero contains a real code or context artifact.
- [ ] Headline is large, compact, and intentionally line-broken.
- [ ] Primary CTA uses the accent color.
- [ ] Core capabilities appear in a ruled numbered grid.
- [ ] At least one section exposes permissions, evidence, or citations.
- [ ] Code examples use Komponist classes, variables, packages, and endpoints.
- [ ] Final CTA is visually distinct without using a gradient.
- [ ] Footer contains a monospaced easter egg.

### Studio

- [ ] Navigation groups match user tasks.
- [ ] Environment is always visible.
- [ ] Metrics distinguish real, simulated, and concept data.
- [ ] Permission denies are visible and understandable.
- [ ] Source health includes text states.
- [ ] Tables remain navigable by keyboard.
- [ ] Low confidence is noticeable but not presented as a fatal error.
- [ ] Charts have accessible text equivalents.
- [ ] Dense layouts still use consistent spacing and alignment.

### Brand QA

- [ ] The only product name shown is Komponist.
- [ ] No legacy package, endpoint, variable, or title remains.
- [ ] The product is described through concrete mechanisms.
- [ ] Humor does not appear in critical operational messages.
- [ ] No generic AI imagery or visual clichés are present.

## 19. Fidelity notes

High-confidence reference characteristics:

- oversized editorial marketing typography;
- developer-focused code artifacts;
- numbered feature and process modules;
- arrows, braces, checks, and other typographic symbols;
- ruled grids and clearly separated sections;
- product explanations built around sources, identity, permissions, evidence, and context;
- a compact Studio with sidebar navigation, metrics, charts, health tables, gaps, and recent requests;
- concise microcopy with dry humor.

Implementation-calibrated values:

- exact font families;
- exact hexadecimal colors;
- exact radii and breakpoint values;
- exact animation durations.

When matching the live reference in a browser, preserve this document’s hierarchy and component behavior first. Adjust calibrated values only when a direct side-by-side comparison demonstrates a mismatch.
