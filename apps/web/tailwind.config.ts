import type { Config } from 'tailwindcss';

// Every color and font references a CSS variable defined in src/styles/tokens.css.
// Components never hardcode hex values.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: 'var(--canvas)',
        surface: 'var(--surface)',
        'surface-hi': 'var(--surface-hi)',
        accent: 'var(--accent)',
        'accent-hi': 'var(--accent-hi)',
        'accent-deep': 'var(--accent-deep)',
        'status-green': 'var(--status-green)',
        'gate-gold': 'var(--gate-gold)',
        danger: 'var(--danger)',
        'sidebar-top': 'var(--sidebar-top)',
        'sidebar-bottom': 'var(--sidebar-bottom)',
        cream: 'var(--text)',
        muted: 'var(--muted)',
        faint: 'var(--faint)',
        line: 'var(--border)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
      },
      borderRadius: {
        glass: '15px',
      },
    },
  },
  plugins: [],
} satisfies Config;
