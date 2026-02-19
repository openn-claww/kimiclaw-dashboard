/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'trader-dark': '#0a0a0f',
        'trader-card': '#151520',
        'trader-border': '#252535',
        'trader-accent': '#00d4ff',
        'trader-success': '#00ff88',
        'trader-danger': '#ff4757',
      }
    },
  },
  plugins: [],
}
