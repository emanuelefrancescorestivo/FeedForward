/**
 * FoodDetailScreen
 * ----------------
 * A food's full scientific profile, powered by /analysis/profile:
 *  - nutrient-density gauge (transparent NRF-style score)
 *  - nutrient contributions as % of daily need (and limit nutrients flagged)
 *  - detected anti-nutrients (phytate/oxalate/tannin) that affect absorption
 *  - goals this food supports, with evidence
 *  - informational cautions (framed as "discuss with your provider")
 *
 * This is the surface where FeedForward stops being a lookup and becomes an
 * analysis tool.
 */
import React from "react";
import { View, Text, ScrollView, StyleSheet, TouchableOpacity } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { analysis } from "../api/client";
import { colors, spacing, radius, typography } from "../theme";
import { EvidenceBadge } from "../components/EvidenceBadge";
import { DensityGauge, NutrientBar, CautionCard } from "../components/FoodProfileParts";
import { ScreenState } from "../components/ScreenState";
import { useProfile } from "../store";

export function FoodDetailScreen({ route, navigation }: any) {
  const { foodId, name } = route.params;
  const professional = useProfile((s) => s.tier === "professional");
  const demographic = useProfile((s) => s.demographic);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["profile", foodId, demographic],
    queryFn: () => analysis.profile(foodId, demographic ?? undefined),
  });

  if (isLoading || error || !data) {
    return (
      <ScreenState loading={isLoading} error={error} empty={!isLoading && !error && !data}
        onRetry={() => refetch()} emptyTitle="Food not found" />
    );
  }

  const beneficial = data.nutrients.filter((n) => n.kind === "beneficial" && (n.percent_of_need ?? 0) > 0).slice(0, 8);
  const limits = data.nutrients.filter((n) => n.kind === "limit" && (n.percent_of_limit ?? 0) > 0);

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: spacing.md }}>
      <Text style={styles.title}>{name}</Text>
      <Text style={styles.category} numberOfLines={2}>{data.category}</Text>

      <DensityGauge score={data.density_score} />

      {data.anti_nutrients.length > 0 && (
        <View style={styles.antiRow}>
          <Text style={styles.antiLabel}>Absorption factors: </Text>
          {data.anti_nutrients.map((a) => (
            <View key={a} style={styles.antiChip}>
              <Text style={styles.antiChipText}>{a}</Text>
            </View>
          ))}
        </View>
      )}

      <Text style={styles.section}>Daily needs covered (per 100g)</Text>
      {beneficial.map((n) => (
        <NutrientBar key={n.nutrient} label={n.nutrient} percent={n.percent_of_need ?? 0} />
      ))}
      {limits.length > 0 && (
        <>
          <Text style={styles.subSection}>Nutrients to limit</Text>
          {limits.map((n) => (
            <NutrientBar key={n.nutrient} label={n.nutrient} percent={n.percent_of_limit ?? 0} isLimit />
          ))}
        </>
      )}

      <Text style={styles.section}>Supports these goals</Text>
      {data.goals_supported.slice(0, 6).map((g) => (
        <TouchableOpacity
          key={g.goal}
          style={styles.goalRow}
          onPress={() => navigation.navigate("Recommendations", { goal: g.goal, label: g.goal.replace(/_/g, " ") })}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.goalName}>{g.goal.replace(/_/g, " ")}</Text>
            <EvidenceBadge evidenceGrade={g.evidence} professional={professional} />
            {professional && g.citations && g.citations.length > 0 && (
              <Text style={styles.cite}>{g.citations.join(", ")}</Text>
            )}
          </View>
          <View style={styles.matchPill}><Text style={styles.matchText}>{Math.round(g.match)}</Text></View>
        </TouchableOpacity>
      ))}

      {data.cautions.length > 0 && (
        <>
          <Text style={styles.section}>Good to know</Text>
          {data.cautions.map((c, i) => (
            <CautionCard key={i} context={c.context} message={c.message}
              disposition={c.disposition} severity={c.severity} />
          ))}
        </>
      )}

      <Text style={styles.disclaimer}>
        For educational purposes only — not medical advice. Consult a qualified
        healthcare provider regarding your health and nutrition.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  centered: { flex: 1, alignItems: "center", justifyContent: "center" },
  title: { ...typography.h1, color: colors.text },
  category: { ...typography.caption, color: colors.textMuted, marginBottom: spacing.sm },
  antiRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6, marginVertical: spacing.sm },
  antiLabel: { ...typography.caption, color: colors.textMuted },
  antiChip: { backgroundColor: "#F3EEE3", borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 3 },
  antiChipText: { ...typography.caption, color: "#8A6D1B", textTransform: "capitalize" },
  section: { ...typography.h3, color: colors.primary, marginTop: spacing.lg, marginBottom: spacing.sm },
  subSection: { ...typography.caption, color: colors.textMuted, marginTop: spacing.md, marginBottom: spacing.sm, fontWeight: "600" },
  goalRow: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.surface,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginBottom: spacing.sm,
  },
  goalName: { ...typography.body, color: colors.text, fontWeight: "600", marginBottom: 4, textTransform: "capitalize" },
  matchPill: { backgroundColor: colors.primary, borderRadius: radius.pill, minWidth: 34, height: 34, alignItems: "center", justifyContent: "center" },
  matchText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  cite: { ...typography.caption, color: colors.accent, marginTop: 4 },
  disclaimer: { ...typography.caption, color: colors.textMuted, fontStyle: "italic", marginTop: spacing.xl, lineHeight: 18 },
});
