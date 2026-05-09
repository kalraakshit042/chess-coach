/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        board: {
          dark: '#769656',
          light: '#eeeed2',
        },
        chess: {
          bg: '#0f1419',
          surface: '#1a2332',
          border: '#2a3a4e',
          muted: '#8faabe',
          text: '#e7ecef',
          accent: '#6096ba',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
