/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      // Institutional light palette. All surfaces/text resolve from these
      // tokens; derived values (alphas/tints) are written as rgba() of the
      // exact palette hex so nothing new is introduced.
      colors: {
        base: {
          DEFAULT: '#F6F7F9', // page background
          deep: '#F6F7F9',
          panel: '#FFFFFF', // surface
          elevated: '#FFFFFF', // surface
          hover: '#EEF0F3', // hover / subtle fill
        },
        edge: {
          DEFAULT: '#E2E5EA', // border
          subtle: '#EEF0F3', // soft divider (surface-underlying tint)
          strong: 'rgba(22, 24, 29, 0.18)', // ink-derived emphasis border
        },
        ink: {
          DEFAULT: '#16181D', // primary text
          soft: '#5A6270', // secondary
          faint: '#8A919E', // muted
          dim: '#8A919E', // muted (placeholders)
        },
        // Accent is ink, not a brand hue. The palette is deliberately
        // monochrome so that green/red carry exactly one meaning: the sign of a
        // percentage change. Do not reintroduce a saturated accent here.
        accent: {
          DEFAULT: '#16181D',
          dim: 'rgba(22, 24, 29, 0.65)', // accent-derived
        },
        pos: {
          DEFAULT: '#0E7C3A',
          dim: 'rgba(14, 124, 58, 0.7)', // pos-derived
        },
        neg: {
          DEFAULT: '#C62828',
          dim: 'rgba(198, 40, 40, 0.7)', // neg-derived
        },
        // Warning semantics reuse the loss red (institutional alert color);
        // keeps every value inside the fixed palette.
        warn: {
          DEFAULT: '#C62828',
          dim: 'rgba(198, 40, 40, 0.7)',
        },
      },
      fontFamily: {
        // The stacks themselves are declared once in src/index.css as
        // --font-sans / --font-mono. Tailwind only references those vars, so a
        // font change cannot drift between utilities and the inline
        // fontFamily props passed to Recharts axis ticks.
        //
        // Archivo is a grotesque with tighter apertures than the previous
        // Inter, which read generic at small sizes; labels and prose only.
        // IBM Plex Mono is fixed-advance, so figures align in columns by font
        // metric rather than by a fragile optional `tnum` feature. All numeric
        // display type uses this face (see the `.num` utility in index.css).
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)'],
      },
      // Fixed type scale (px). Body line-height 1.5, headings 1.2.
      fontSize: {
        '11px': ['11px', '1.5'],
        xs: ['12px', '1.5'],
        sm: ['14px', '1.5'],
        base: ['16px', '1.5'],
        lg: ['20px', '1.2'],
        xl: ['24px', '1.2'],
        '2xl': ['32px', '1.2'],
      },
      boxShadow: {
        // Elevation is removed entirely: surfaces are separated by 1px
        // hairline borders, never by blur. `shadow-panel` is retained as a
        // token name so the ~9 existing call sites stay valid and resolve to
        // a flat, sharp surface.
        panel: 'none',
        'accent-glow': 'none',
      },
      // Square geometry is the default. No `rounded-*` scale is provided on
      // purpose, so a rounded corner cannot be introduced by accident.
      borderRadius: {
        none: '0px',
      },
      borderColor: {
        DEFAULT: '#E2E5EA',
      },
    },
  },
  plugins: [],
}