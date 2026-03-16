import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
      },
      colors: {
        // Dark theme surfaces — map CSS variables to Tailwind tokens
        dark: {
          bg: "#1a1c22",
          surface: "#20232b",
          card: "#252830",
          border: "#2e3140",
          hover: "#2a2d38",
        },
        // Accent — primary CTAs, active states
        accent: {
          DEFAULT: "#7b8cde",
          strong: "#a0aaf0",
          dim: "#5a6aaa",
          muted: "rgba(123,140,222,0.10)",
          glow: "rgba(123,140,222,0.18)",
        },
        // Text shades on dark
        ink: {
          DEFAULT: "#e8eaf2",
          muted: "#8b91a8",
          faint: "#565c73",
        },
        // Status colors
        status: {
          success: "#16a34a",
          warning: "#c2410c",
          danger: "#dc2626",
        },
        // Severity — for issue/node coloring
        severity: {
          high: "#dc2626",
          medium: "#ea580c",
          core_value: "#16a34a",
          recommendation_affected: "#5a6272",
          normal: "#6b7280",
        },
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(46,49,64,0.8)",
        glow: "0 0 16px rgba(123,140,222,0.12)",
        "glow-sm": "0 0 8px rgba(123,140,222,0.08)",
        // Phase 1 chat card subtle border
        "chat-glow": "0 0 0 1px rgba(46,49,64,0.8), 0 2px 16px rgba(0,0,0,0.3)",
        // Button accent shadow on hover
        "btn-accent": "0 2px 8px rgba(123,140,222,0.25)",
      },
      fontSize: {
        "2xs": ["11px", { letterSpacing: "0.05em" }],
      },
    },
  },
  plugins: [],
};

export default config;
