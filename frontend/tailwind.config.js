/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./public/index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef7ff",
          100: "#d9ecff",
          200: "#bcdcff",
          300: "#8ec6ff",
          400: "#5ea9ff",
          500: "#3a86ff",
          600: "#2d67e6",
          700: "#244ec0",
          800: "#213f98",
          900: "#1f387b",
        },
        ink: "#0b1020",
      },
      boxShadow: {
        card: "0 10px 30px -12px rgba(0,0,0,0.35)",
      },
      backgroundImage: {
        "hero-gradient": "radial-gradient(1200px 500px at 10% -10%, rgba(58,134,255,0.25), rgba(0,0,0,0)), radial-gradient(800px 400px at 90% -10%, rgba(99,102,241,0.28), rgba(0,0,0,0))",
      }
    },
  },
  plugins: [],
}
