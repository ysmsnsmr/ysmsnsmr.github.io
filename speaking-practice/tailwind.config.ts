import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        paper: "rgb(var(--sp-color-paper-rgb) / <alpha-value>)",
        ink: "rgb(var(--sp-color-ink-rgb) / <alpha-value>)",
        calm: "rgb(var(--sp-color-calm-rgb) / <alpha-value>)",
        "calm-soft": "rgb(var(--sp-color-calm-soft-rgb) / <alpha-value>)",
        honey: "rgb(var(--sp-color-honey-rgb) / <alpha-value>)",
        coral: "rgb(var(--sp-color-coral-rgb) / <alpha-value>)"
      },
      boxShadow: {
        soft: "var(--sp-shadow-soft)"
      }
    }
  },
  plugins: []
};

export default config;
