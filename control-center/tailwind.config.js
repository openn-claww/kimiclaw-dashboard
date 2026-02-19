/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        'dark': '#0a0a0f',
        'darker': '#050508',
        'card': '#151520',
        'card-hover': '#1a1a2e',
        'border': '#252535',
        'accent': '#00d4ff',
        'accent-hover': '#00b8e6',
        'success': '#00ff88',
        'success-dim': 'rgba(0, 255, 136, 0.1)',
        'danger': '#ff4757',
        'danger-dim': 'rgba(255, 71, 87, 0.1)',
        'warning': '#ffa502',
        'warning-dim': 'rgba(255, 165, 2, 0.1)',
        'info': '#74b9ff',
        'purple': '#a29bfe',
        'pink': '#fd79a8',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'float': 'float 6s ease-in-out infinite',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        }
      }
    },
  },
  plugins: [],
}
