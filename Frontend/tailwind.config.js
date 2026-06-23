/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        blueprint: {
          bg: '#0F172A',
          card: '#1E293B',
          line: '#2A3B57',
          gold: '#D4AF37',
          goldSoft: 'rgba(212,175,55,0.15)',
          text: '#F8FAFC',
          muted: '#94A3B8',
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['"Inter"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      backgroundImage: {
        'blueprint-grid':
          'linear-gradient(rgba(212,175,55,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(212,175,55,0.06) 1px, transparent 1px)',
      },
      backgroundSize: {
        grid: '32px 32px',
      },
      boxShadow: {
        gold: '0 0 0 1px rgba(212,175,55,0.4), 0 8px 24px -8px rgba(212,175,55,0.25)',
      },
      keyframes: {
        draw: {
          '0%': { strokeDashoffset: 1000 },
          '100%': { strokeDashoffset: 0 },
        },
        pulseGlow: {
          '0%,100%': { opacity: 0.5 },
          '50%': { opacity: 1 },
        },
      },
      animation: {
        draw: 'draw 2.4s ease forwards',
        pulseGlow: 'pulseGlow 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
