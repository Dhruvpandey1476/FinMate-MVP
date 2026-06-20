/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#070A12",
        surface: "#0D1220",
        panel: "#11172A",
        line: "#1E2740",
        mint: "#27E0A6",
        violet: "#8B7CFF",
        gold: "#F0B860",
        rose: "#FF6B7A",
        fog: "#A8B2C9",
        mist: "#5E6A87",
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"],
        body: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      backgroundImage: {
        "twin-glow": "radial-gradient(circle at 20% 0%, rgba(139,124,255,0.18), transparent 45%), radial-gradient(circle at 90% 10%, rgba(39,224,166,0.14), transparent 40%)",
      },
      boxShadow: {
        glass: "0 8px 32px rgba(0,0,0,0.35)",
        glow: "0 0 24px rgba(39,224,166,0.25)",
      },
    },
  },
  plugins: [],
};
