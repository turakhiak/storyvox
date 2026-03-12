/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Warm, cinematic palette — like a vintage theater
        ink: {
          50: "#faf8f6",
          100: "#f0ebe5",
          200: "#e0d5c9",
          300: "#c9b8a5",
          400: "#b09780",
          500: "#9a7d65",
          600: "#846856",
          700: "#6b5347",
          800: "#59463e",
          900: "#4c3d37",
          950: "#1c1614",
        },
        amber: {
          warm: "#E8A838",
          glow: "#F5C561",
        },
        stage: {
          red: "#C94C4C",
          blue: "#4A6FA5",
          green: "#6B9080",
          purple: "#7B506F",
        },
        surface: {
          light: "#FAF7F2",
          DEFAULT: "#F2EDE4",
          dark: "#0D0B09",
          elevated: "#1A1714",
        },
      },
      fontFamily: {
        display: ['"Playfair Display"', "Georgia", "serif"],
        body: ['"Source Serif 4"', "Georgia", "serif"],
        mono: ['"JetBrains Mono"', "monospace"],
        ui: ['"DM Sans"', "system-ui", "sans-serif"],
      },
      animation: {
        "fade-in": "fadeIn 0.5s ease-out",
        "slide-up": "slideUp 0.5s ease-out",
        "slide-in-right": "slideInRight 0.3s ease-out",
        "pulse-soft": "pulseSoft 2s ease-in-out infinite",
        "waveform": "waveform 1.2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideInRight: {
          "0%": { opacity: "0", transform: "translateX(16px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
        waveform: {
          "0%, 100%": { height: "4px" },
          "50%": { height: "20px" },
        },
      },
    },
  },
  plugins: [],
};
