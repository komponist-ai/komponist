/**
 * Reagraph themes built from the Komponist design tokens.
 *
 * These are the same warm paper/orange/teal values the rest of Studio uses, so
 * the graph reads as part of the product rather than as an embedded widget.
 * The values are literals rather than `var(--color-…)` lookups because they end
 * up inside a WebGL canvas, where CSS custom properties do not resolve.
 */

import type { Theme as ReagraphTheme } from 'reagraph'
import type { Theme } from '../ThemeProvider'

const lightGraphTheme: ReagraphTheme = {
  // Fog is off: the layout is flat, so depth haze only dulls the entity
  // colours without adding any depth cue.
  canvas: { background: '#f6eedf', fog: null },
  node: {
    // Per-node `fill` overrides this; it only shows for an untyped entity.
    fill: '#9a9184',
    activeFill: '#e8641b',
    opacity: 1,
    selectedOpacity: 1,
    // Everything outside the focused neighborhood fades rather than vanishes,
    // so the shape of the wider graph stays legible.
    inactiveOpacity: 0.15,
    label: {
      color: '#201c15',
      stroke: '#fdf9f1',
      activeColor: '#c2500d',
    },
    subLabel: {
      color: '#6b6257',
      stroke: '#fdf9f1',
      activeColor: '#c2500d',
    },
  },
  ring: {
    fill: '#d9cfbf',
    activeFill: '#e8641b',
  },
  edge: {
    fill: '#c8bcaa',
    activeFill: '#e8641b',
    opacity: 0.75,
    selectedOpacity: 1,
    inactiveOpacity: 0.08,
    label: {
      color: '#6b6257',
      stroke: '#fdf9f1',
      activeColor: '#c2500d',
      fontSize: 5,
    },
  },
  arrow: {
    fill: '#c8bcaa',
    activeFill: '#e8641b',
  },
  lasso: {
    background: 'rgba(232, 100, 27, 0.12)',
    border: '1px solid #e8641b',
  },
}

const darkGraphTheme: ReagraphTheme = {
  canvas: { background: '#181510', fog: null },
  node: {
    fill: '#7d7468',
    activeFill: '#f47b35',
    opacity: 1,
    selectedOpacity: 1,
    inactiveOpacity: 0.12,
    label: {
      color: '#f7efe2',
      stroke: '#100e0b',
      activeColor: '#ff9a5f',
    },
    subLabel: {
      color: '#aba092',
      stroke: '#100e0b',
      activeColor: '#ff9a5f',
    },
  },
  ring: {
    fill: '#3b342b',
    activeFill: '#f47b35',
  },
  edge: {
    fill: '#655b4e',
    activeFill: '#f47b35',
    opacity: 0.8,
    selectedOpacity: 1,
    inactiveOpacity: 0.07,
    label: {
      color: '#aba092',
      stroke: '#100e0b',
      activeColor: '#ff9a5f',
      fontSize: 5,
    },
  },
  arrow: {
    fill: '#655b4e',
    activeFill: '#f47b35',
  },
  lasso: {
    background: 'rgba(244, 123, 53, 0.12)',
    border: '1px solid #f47b35',
  },
}

/** The accent a selection ring is drawn in, per theme. */
export const SELECTION_RING_COLOR: Record<Theme, string> = {
  light: '#e8641b',
  dark: '#f47b35',
}

/** The accent the focused node is ringed in, distinct from selection. */
export const FOCUS_RING_COLOR: Record<Theme, string> = {
  light: '#0e8a7d',
  dark: '#43b9ac',
}

export function graphTheme(theme: Theme): ReagraphTheme {
  return theme === 'dark' ? darkGraphTheme : lightGraphTheme
}
