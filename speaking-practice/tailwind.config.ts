import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        paper: "#F8F4EA",
        ink: "#1F2933",
        calm: "#0F766E",
        "calm-soft": "#DDF5EF",
        honey: "#F5C542",
        coral: "#F9735B"
      },
      boxShadow: {
        soft: "0 18px 45px rgba(31, 41, 51, 0.10)"
      }
    }
  },
  plugins: []
};

export default config;
