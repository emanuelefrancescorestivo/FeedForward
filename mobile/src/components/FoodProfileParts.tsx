/**
 * Components for the scientific food profile:
 *  - DensityGauge: the 0-100 nutrient-density score as a ring.
 *  - NutrientBar: a nutrient's contribution as % of daily need (or limit).
 *  - CautionCard: an informational food-drug/condition flag.
 */
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, radius, spacing, typography } from "../theme";

export function DensityGauge({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score));
  // color from limited (amber) to dense (teal)
  const color = pct >= 60 ? colors.gradeA : pct >= 30 ? colors.gradeB : colors.gradeC;
  return (
    <View style={styles.gaugeWrap}>
      <View style={[styles.gaugeCircle, { borderColor: color }]}>
        <Text style={[styles.gaugeScore, { color }]}>{Math.round(pct)}</Text>
        <Text style={styles.gaugeMax}>/100</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.gaugeLabel}>Nutrient density</Text>
        <Text style={styles.gaugeSub}>
          Beneficial nutrients per calorie, minus nutrients to limit. Transparent
          NRF-style index.
        </Text>
      </View>
    </View>
  );
}

export function NutrientBar({
  label,
  percent,
  isLimit = false,
}: {
  label: string;
  percent: number;
  isLimit?: boolean;
}) {
  const width = Math.max(2, Math.min(100, percent));
  const barColor = isLimit ? colors.warning : colors.primary;
  return (
    <View style={styles.barRow}>
      <Text style={styles.barLabel} numberOfLines={1}>{label.replace(/-/g, " ")}</Text>
      <View style={styles.barTrack}>
        <View style={[styles.barFill, { width: `${width}%`, backgroundColor: barColor }]} />
      </View>
      <Text style={styles.barPct}>
        {Math.round(percent)}%{isLimit ? " limit" : ""}
      </Text>
    </View>
  );
}

export function CautionCard({
  context,
  message,
  disposition,
  severity,
}: {
  context: string;
  message: string;
  disposition: string;
  severity: string;
}) {
  const tone =
    severity === "important" ? colors.warning : severity === "moderate" ? colors.gradeC : colors.textMuted;
  return (
    <View style={[styles.cautionCard, { borderLeftColor: tone }]}>
      <Text style={[styles.cautionContext, { color: tone }]}>{context}</Text>
      <Text style={styles.cautionMsg}>{message}</Text>
      <Text style={styles.cautionDisp}>{disposition}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  gaugeWrap: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginVertical: spacing.sm },
  gaugeCircle: {
    width: 68, height: 68, borderRadius: 34, borderWidth: 5,
    alignItems: "center", justifyContent: "center",
  },
  gaugeScore: { fontSize: 22, fontWeight: "700" },
  gaugeMax: { fontSize: 10, color: colors.textMuted, marginTop: -2 },
  gaugeLabel: { ...typography.h3, color: colors.text },
  gaugeSub: { ...typography.caption, color: colors.textMuted, lineHeight: 17 },

  barRow: { flexDirection: "row", alignItems: "center", marginBottom: 6, gap: spacing.sm },
  barLabel: { ...typography.caption, color: colors.text, width: 96, textTransform: "capitalize" },
  barTrack: { flex: 1, height: 8, backgroundColor: colors.border, borderRadius: radius.pill, overflow: "hidden" },
  barFill: { height: 8, borderRadius: radius.pill },
  barPct: { ...typography.caption, color: colors.textMuted, width: 64, textAlign: "right" },

  cautionCard: {
    backgroundColor: colors.surface, borderRadius: radius.sm, borderWidth: 1,
    borderColor: colors.border, borderLeftWidth: 4, padding: spacing.md, marginBottom: spacing.sm,
  },
  cautionContext: { ...typography.h3, marginBottom: 4, textTransform: "capitalize" },
  cautionMsg: { ...typography.body, color: colors.text, lineHeight: 20 },
  cautionDisp: { ...typography.caption, color: colors.textMuted, fontStyle: "italic", marginTop: 6, lineHeight: 17 },
});
