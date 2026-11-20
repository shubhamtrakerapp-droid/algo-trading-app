/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#0b0e14',
        surface: '#121721',
        card: '#181f2c',
        border: '#232b3b',
        primary: {
          DEFAULT: '#3b82f6',
          hover: '#2563eb',
        },
        profit: '#10b981',
        loss: '#ef4444',
        warning: '#f59e0b',
        accent: '#8b5cf6',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Courier New', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
