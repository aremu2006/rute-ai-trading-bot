/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#09090b', // Deep almost black
        surface: '#18181b',    // Slightly lighter for cards
        primary: '#3b82f6',    // Electric Blue
        secondary: '#8b5cf6',  // Violet
        accent: '#10b981',     // Neon Green
        danger: '#ef4444',     // Neon Red
        muted: '#71717a',      // Gray text
        border: '#27272a',     // Subtle borders
        glass: 'rgba(24, 24, 27, 0.7)',
      },
      fontFamily: {
        sans: ['system-ui', 'sans-serif'],
        mono: ['Menlo', 'monospace'],
      },
      animation: {
        'slide-in': 'slideIn 0.3s ease-out',
        'fade-in': 'fadeIn 0.2s ease-in',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        slideIn: {
          '0%': { transform: 'translateY(-10px)', opacity: 0 },
          '100%': { transform: 'translateY(0)', opacity: 1 },
        },
        fadeIn: {
          '0%': { opacity: 0 },
          '100%': { opacity: 1 },
        },
      },
    },
  },
  plugins: [],
}
