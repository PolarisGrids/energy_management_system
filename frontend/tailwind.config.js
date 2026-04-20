/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Polaris Brand Colors
        'polaris-blue':  '#0A3690',
        'energy-green':  '#02C9A8',
        'accent-blue':   '#ABC7FF',
        'light-gray':    '#F3F9F9',
        'dark-navy':     '#0A2870',
        'sky-blue':      '#56CCF2',
        'medium-blue':   '#2F80ED',
        // Status colors
        'status-critical': '#E94B4B',
        'status-high':     '#F97316',
        'status-medium':   '#F59E0B',
        'status-low':      '#3B82F6',
        'status-ok':       '#02C9A8',
      },
      fontFamily: {
        sans: ['Satoshi', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
      },
      fontSize: {
        'h1': ['48px', { lineHeight: '56px', letterSpacing: '0' }],
        'h2': ['36px', { lineHeight: '44px', letterSpacing: '0' }],
        'h3': ['28px', { lineHeight: '36px', letterSpacing: '0.04em' }],
        'sub': ['20px', { lineHeight: '28px' }],
        'body1': ['16px', { lineHeight: '24px' }],
        'body2': ['14px', { lineHeight: '20px' }],
        'caption': ['12px', { lineHeight: '16px' }],
        'label': ['11px', { lineHeight: '16px', letterSpacing: '0.05em' }],
      },
      backgroundImage: {
        'gradient-primary':   'linear-gradient(45deg, #11ABBE, #3C63FF, #37AAFE)',
        'gradient-secondary': 'linear-gradient(45deg, #02C9A8, #11ABBE)',
        'gradient-tertiary':  'linear-gradient(-45deg, #2F80ED, #56CCF2)',
        'gradient-sidebar':   'linear-gradient(180deg, #0A3690, #0A2870)',
      },
      boxShadow: {
        'card':    '0 2px 8px rgba(0,0,0,0.08)',
        'glow':    '0 0 40px rgba(2,201,168,0.4), 0 0 20px rgba(17,171,190,0.3)',
        'glow-sm': '0 0 20px rgba(2,201,168,0.3)',
        'modal':   '0 20px 60px rgba(0,0,0,0.15)',
        'nav':     '0 8px 24px rgba(10,54,144,0.15)',
      },
      backdropBlur: {
        'glass': '20px',
      },
      borderRadius: {
        'card': '12px',
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
      screens: {
        'xs': '480px',
      },
      animation: {
        'shimmer': 'shimmer 1.5s infinite',
        'slide-up': 'slideUp 500ms ease-in-out',
        'pulse-slow': 'pulse 3s infinite',
        'ping-slow': 'ping 2s infinite',
      },
      keyframes: {
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
