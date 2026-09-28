/**
 * Design tokens for the FeedForward app.
 * A single source of truth so consumer and professional surfaces stay coherent.
 */
export const colors = {
  primary: "#0F6E56",       // FeedForward teal
  primaryLight: "#E1F5EE",
  accent: "#534AB7",        // evidence/science purple
  bg: "#FBFAF7",
  surface: "#FFFFFF",
  border: "#E7E5DE",
  text: "#1D1D1B",
  textMuted: "#6B6A65",
  // evidence grade colors
  gradeA: "#1D9E75",
  gradeB: "#639922",
  gradeC: "#BA7517",
  gradeD: "#888780",
  warning: "#A32D2D",
};

export const grade = {
  A: { color: colors.gradeA, label: "Strongly supported by research" },
  B: { color: colors.gradeB, label: "Well supported by research" },
  C: { color: colors.gradeC, label: "Some supporting evidence" },
  D: { color: colors.gradeD, label: "Emerging evidence" },
} as const;

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 };

export const radius = { sm: 8, md: 12, lg: 16, pill: 999 };

export const typography = {
  h1: { fontSize: 26, fontWeight: "600" as const },
  h2: { fontSize: 20, fontWeight: "600" as const },
  h3: { fontSize: 16, fontWeight: "600" as const },
  body: { fontSize: 15, fontWeight: "400" as const },
  caption: { fontSize: 13, fontWeight: "400" as const },
};
