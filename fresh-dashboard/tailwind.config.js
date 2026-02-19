/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        dark: '#0a0a0f',
        card: '#151520',
        border: '#252535',
        accent: '#00d4ff',
        success: '#00ff88',
        danger: '#ff4757',
        warning: '#ffa502'
      }
    },
  },
  plugins: [],
}
