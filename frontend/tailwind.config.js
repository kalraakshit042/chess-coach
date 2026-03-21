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
          bg: '#161512',
          surface: '#1e1d1a',
          border: '#2d2b28',
          muted: '#3d3b37',
          text: '#bababa',
          accent: '#c0a060',
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
