/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        base: {
          DEFAULT: '#0b0e14',
          deep: '#080a0f',
          panel: '#0f131b',
          elevated: '#161b26',
          hover: '#1b2230',
        },
        edge: {
          DEFAULT: '#232b3a',
          subtle: '#1b2230',
          strong: '#2e3a4e',
        },
        ink: {
          DEFAULT: '#dde4ee',
          soft: '#9aa7ba',
          faint: '#6d7a8f',
          dim: '#5d6b80',
        },
        accent: {
          DEFAULT: '#4cc2ff',
          dim: '#2d7fb8',
          glow: '#4cc2ff',
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
      fontSize: {
        xs: ['11px', '1.25rem'],
        sm: ['12px', '1.375rem'],
        base: ['13px', '1.5rem'],
        lg: ['14px', '1.5rem'],
        xl: ['16px', '1.5rem'],
        '2xl': ['20px', '1.4rem'],
        '3xl': ['24px', '1.3rem'],
        '4xl': ['32px', '1.2rem'],
      },
      boxShadow: {
        panel: '0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)',
        'accent-glow': '0 0 0 1px rgba(76,194,255,0.35), 0 4px 18px -6px rgba(76,194,255,0.35)',
      },
      borderColor: {
        DEFAULT: '#232b3a',
      },
    },
  },
  plugins: [],
}