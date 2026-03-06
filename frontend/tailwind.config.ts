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
          bg: "#080c14",
          surface: "#0f1623",
          card: "#141d2e",
          border: "#1e2d45",
          hover: "#192236",
        },
        // Accent — primary CTAs, active states (desaturated cyan)
        accent: {
          DEFAULT: "#19b7c0",
          strong: "#22d3ee",
          dim: "#0891b2",
          muted: "rgba(25,183,192,0.12)",
          glow: "rgba(25,183,192,0.25)",
        },
        // Text shades on dark
        ink: {
          DEFAULT: "#e2e8f0",
          muted: "#7a91b0",
          faint: "#3d5270",
        },
        // Status colors
        status: {
          success: "#22c55e",
          warning: "#f59e0b",
          danger: "#ef4444",
        },
        // Severity — for issue/node coloring
        severity: {
          high: "#ef4444",
          medium: "#f97316",
          core_value: "#22c55e",
          recommendation_affected: "#22d3ee",
          normal: "#334155",
        },
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(30,45,69,0.8)",
        glow: "0 0 16px rgba(25,183,192,0.2)",
        "glow-sm": "0 0 8px rgba(25,183,192,0.15)",
        // Phase 1 chat card glow border
        "chat-glow": "0 0 0 1px rgba(25,183,192,0.15), 0 0 32px rgba(25,183,192,0.06)",
        // Button accent glow on hover
        "btn-accent": "0 0 12px rgba(25,183,192,0.3)",
      },
      fontSize: {
        "2xs": ["11px", { letterSpacing: "0.05em" }],
      },
    },
  },
  plugins: [],
};

export default config;
