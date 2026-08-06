/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Paper surfaces
        paper: 'var(--color-paper)',
        'paper-2': 'var(--color-paper-2)',
        'paper-3': 'var(--color-paper-3)',
        white: 'var(--color-white)',

        // Text
        ink: 'var(--color-ink)',
        'ink-2': 'var(--color-ink-2)',
        muted: 'var(--color-muted)',
        faint: 'var(--color-faint)',

        // Lines
        line: 'var(--color-line)',

        // Brand accent - Orange
        orange: 'var(--color-orange)',
        'orange-dark': 'var(--color-orange-dark)',
        'orange-light': 'var(--color-orange-light)',

        // Secondary accent - Teal
        teal: 'var(--color-teal)',
        'teal-light': 'var(--color-teal-light)',

        // Semantic
        success: 'var(--color-success)',
        'success-soft': 'var(--color-success-soft)',
        warning: 'var(--color-warning)',
        'warning-soft': 'var(--color-warning-soft)',
        danger: 'var(--color-danger)',
        'danger-soft': 'var(--color-danger-soft)',
        info: 'var(--color-info)',
        'info-soft': 'var(--color-info-soft)',

        // Code
        'code-bg': 'var(--color-code-bg)',
        'code-surface': 'var(--color-code-surface)',
        'code-text': 'var(--color-code-text)',
        'code-muted': 'var(--color-code-muted)',
        'code-keyword': 'var(--color-code-keyword)',
        'code-string': 'var(--color-code-string)',
        'code-number': 'var(--color-code-number)',
        'code-comment': 'var(--color-code-comment)',

        // Focus
        focus: 'var(--color-focus)',
      },
      fontFamily: {
        display: ['Arial Rounded MT Bold', 'Avenir Next Rounded', 'Nunito', 'sans-serif'],
        body: ['Arial Rounded MT Bold', 'Avenir Next Rounded', 'Nunito', 'sans-serif'],
        mono: ['JetBrains Mono', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      fontSize: {
        hero: 'var(--text-hero)',
        display: 'var(--text-display)',
        h1: 'var(--text-h1)',
        h2: 'var(--text-h2)',
        h3: 'var(--text-h3)',
        lead: 'var(--text-lead)',
        body: 'var(--text-body)',
        small: 'var(--text-small)',
        caption: 'var(--text-caption)',
        micro: 'var(--text-micro)',
      },
      maxWidth: {
        site: 'var(--container-max)',
        reading: 'var(--container-reading)',
      },
      borderRadius: {
        none: '0',
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        pill: 'var(--radius-pill)',
      },
      boxShadow: {
        none: 'var(--shadow-none)',
        subtle: 'var(--shadow-subtle)',
        card: 'var(--shadow-card)',
        popover: 'var(--shadow-popover)',
      },
      transitionDuration: {
        fast: 'var(--duration-fast)',
        base: 'var(--duration-base)',
        slow: 'var(--duration-slow)',
      },
      spacing: {
        sidebar: 'var(--sidebar-width)',
        'gutter-mobile': 'var(--gutter-mobile)',
        'gutter-tablet': 'var(--gutter-tablet)',
        'gutter-desktop': 'var(--gutter-desktop)',
      },
    },
  },
  plugins: [],
}
