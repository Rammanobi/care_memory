/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#FAF7F2",
        ink: "#1F2933",
        teal: { DEFAULT: "#0F766E", bg: "#E6F2F0" },
        saf: { DEFAULT: "#F59E0B", bg: "#FEF3DC" },
        red: { DEFAULT: "#B91C1C", bg: "#FBE9E9" },
        green: { DEFAULT: "#15803D", bg: "#E4F3E9" },
        blue: { DEFAULT: "#1D4ED8", bg: "#E3ECFD" },
        mute: "#5B6670",
        line: "#E6DFD3",
      },
      fontFamily: { sans: ['"Segoe UI"', "Arial", "sans-serif"] },
    },
  },
  plugins: [],
};
