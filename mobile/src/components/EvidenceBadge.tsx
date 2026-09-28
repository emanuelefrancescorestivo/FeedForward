/**
 * EvidenceBadge
 * -------------
 * The visual heart of FeedForward's credibility. In consumer mode it shows a
 * plain-language confidence label with a coloured dot; in professional mode it
 * additionally shows the letter grade and (elsewhere) citations.
 */
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, grade, radius, spacing } from "../theme";

type GradeKey = "A" | "B" | "C" | "D";

export function EvidenceBadge({
  evidenceGrade,
  consumerLabel,
  professional = false,
}: {
  evidenceGrade?: string;
  consumerLabel?: string;
  professional?: boolean;
}) {
  const key = (evidenceGrade as GradeKey) in grade ? (evidenceGrade as GradeKey) : undefined;
  const meta = key ? grade[key] : undefined;
  const dotColor = meta?.color ?? colors.gradeC;
  const label = consumerLabel || meta?.label || "Supporting evidence";

  return (
    <View style={styles.row}>
      <View style={[styles.dot, { backgroundColor: dotColor }]} />
      <Text style={styles.label}>{label}</Text>
      {professional && key && (
        <View style={[styles.gradePill, { borderColor: dotColor }]}>
          <Text style={[styles.gradeText, { color: dotColor }]}>Grade {key}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  dot: { width: 10, height: 10, borderRadius: radius.pill },
  label: { fontSize: 13, color: colors.textMuted, flexShrink: 1 },
  gradePill: {
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: 6,
    paddingVertical: 1,
    marginLeft: spacing.xs,
  },
  gradeText: { fontSize: 11, fontWeight: "600" },
});
