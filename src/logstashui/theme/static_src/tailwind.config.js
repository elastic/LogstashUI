// tailwind.config.js
export default {
  content: [
    "../templates/**/*.html",
    "../../templates/**/*.html",
    "./src/**/*.{html,js}"
  ],
  theme: {
    extend: {},
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: [
      {
        eui: {
          "primary": "#006BB4",   // Elastic blue
          "secondary": "#00BFB3", // Teal
          "accent": "#DD0A73",    // Pink
          "neutral": "#343741",   // Kibana dark gray
          "base-100": "#FFFFFF",  // White
          "info": "#017D73",
          "success": "#007C92",
          "warning": "#FEC514",
          "error": "#BD271E",
        },
      },
      {
        euiDark: {
          "primary": "#1BA9F5",     // Elastic blue
          "secondary": "#33BEBE",   // Teal
          "accent": "#F04E98",      // Pink accent
          "neutral": "#25262E",     // Panel gray
          "base-100": "#1D1E24",    // Background
          "base-content": "#D4D4D4",// Text
          "info": "#36A2EF",
          "success": "#7DDED8",
          "warning": "#FEC514",
          "error": "#BD271E",
        },
      }
    ],
  },
}
