/** @type {import('tailwindcss').Config} */

// Every colour resolves through a CSS variable holding an "R G B" triple, so a
// single `data-theme` swap retints the whole app and no component needs to know
// which theme is active. `<alpha-value>` keeps Tailwind's /opacity modifiers working.
const v = (name) => `rgb(var(${name}) / <alpha-value>)`;

module.exports = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: v("--c-ink"),
        surface: v("--c-surface"),
        panel: v("--c-panel"),
        line: v("--c-line"),
        mint: v("--c-mint"),
        violet: v("--c-violet"),
        gold: v("--c-gold"),
        rose: v("--c-rose"),
        fog: v("--c-fog"),
        mist: v("--c-mist"),

        // `white` is remapped to the primary foreground. Existing `text-white`
        // becomes near-black in light mode, and `bg-white/[0.04]` overlays
        // invert into a subtle dark wash — both correct, with no edits.
        white: v("--c-fg"),

        // Text that sits on a mint/violet accent. Stays dark in both themes
        // because the accents are light in both.
        onaccent: v("--c-on-accent"),
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"],
        body: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      backgroundImage: {
        "twin-glow": "var(--bg-glow)",
      },
      boxShadow: {
        glass: "var(--shadow-glass)",
        glow: "var(--shadow-glow)",
        lift: "var(--shadow-lift)",
      },
      transitionTimingFunction: {
        swift: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [],
};
