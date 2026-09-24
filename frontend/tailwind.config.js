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
        accent: {
          DEFAULT: '#0B5FFF',
          dim: 'rgba(11, 95, 255, 0.65)', // accent-derived
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
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Consolas',
          'Liberation Mono',
          'monospace',
        ],
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
        // Single soft elevation token for cards/panels on light.
        panel: '0 1px 2px rgba(22, 24, 29, 0.06)',
        'accent-glow': 'none',
      },
      borderColor: {
        DEFAULT: '#E2E5EA',
      },
    },
  },
  plugins: [],
}