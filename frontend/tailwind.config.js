/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        base: {
          DEFAULT: '#000000',
          deep: '#000000',
          panel: '#000000',
          elevated: '#0d0d0d',
          hover: '#0d0d0d',
        },
        edge: {
          DEFAULT: 'rgba(255, 255, 255, 0.12)',
          subtle: 'rgba(255, 255, 255, 0.05)',
          strong: 'rgba(255, 255, 255, 0.22)',
        },
        ink: {
          DEFAULT: '#ffffff',
          soft: '#a3a3a3',
          faint: '#808080',
          dim: '#5e5e5e',
        },
        accent: {
          DEFAULT: '#4cc2ff',
          dim: '#2d7fb8',
        },
        pos: {
          DEFAULT: '#16c98e',
          dim: '#0e8f67',
        },
        neg: {
          DEFAULT: '#ff5c6c',
          dim: '#c13a4c',
        },
        warn: {
          DEFAULT: '#f5c15c',
          dim: '#a97f2e',
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
        xs: ['12px', '1.5'],
        sm: ['14px', '1.5'],
        base: ['16px', '1.5'],
        lg: ['20px', '1.2'],
        xl: ['24px', '1.2'],
        '2xl': ['32px', '1.2'],
      },
      boxShadow: {
        panel: 'none',
        'accent-glow': 'none',
      },
      borderColor: {
        DEFAULT: 'rgba(255, 255, 255, 0.12)',
      },
    },
  },
  plugins: [],
}