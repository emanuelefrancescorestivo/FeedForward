/**
 * MealPlannerScreen
 * -----------------
 * Builds a calorie-bounded meal optimised (via the backend ILP) to maximise
 * absorbable, well-evidenced nutrient delivery toward a chosen goal.
 */
import React, { useState } from "react";
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator,
} from "react-native";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { useProfile } from "../store";
import { colors, spacing, radius, typography } from "../theme";

const GOALS = [
  { id: "muscle_recovery", label: "Muscle Recovery" },
  { id: "heart_health", label: "Heart Health" },
  { id: "energy_metabolism", label: "Energy" },
  { id: "immune_support", label: "Immune Support" },
];
const BUDGETS = [400, 600, 800];

export function MealPlannerScreen() {
  const [goal, setGoal] = useState(GOALS[0].id);
  const [budget, setBudget] = useState(600);

  const constraints = useProfile((s) => s.dietaryDefaults);
  const plan = useMutation({
    mutationFn: () => api.mealPlan(goal, budget, 3, constraints),
  });

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: spacing.md }}>
      <Text style={styles.title}>Meal Planner</Text>
      <Text style={styles.subtitle}>
        We'll find the best combination of foods under your calorie budget.
      </Text>

      <Text style={styles.label}>Goal</Text>
      <View style={styles.chipRow}>
        {GOALS.map((g) => (
          <TouchableOpacity key={g.id}
            style={[styles.chip, goal === g.id && styles.chipOn]}
            onPress={() => setGoal(g.id)}>
            <Text style={[styles.chipText, goal === g.id && styles.chipTextOn]}>{g.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.label}>Calorie budget</Text>
      <View style={styles.chipRow}>
        {BUDGETS.map((b) => (
          <TouchableOpacity key={b}
            style={[styles.chip, budget === b && styles.chipOn]}
            onPress={() => setBudget(b)}>
            <Text style={[styles.chipText, budget === b && styles.chipTextOn]}>{b} kcal</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity style={styles.button} onPress={() => plan.mutate()}>
        <Text style={styles.buttonText}>Build my meal</Text>
      </TouchableOpacity>

      {plan.isPending && <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.lg }} />}
      {plan.isError && (
        <Text style={styles.infeasible}>Couldn't build a meal. Is the API running?</Text>
      )}

      {plan.data && (
        <View style={styles.result}>
          {plan.data.feasible ? (
            <>
              <Text style={styles.resultHead}>
                {plan.data.total_kcal.toFixed(0)} kcal · {plan.data.items.length} foods
              </Text>
              {plan.data.items.map((it) => (
                <View key={it.food_id} style={styles.mealItem}>
                  <Text style={styles.mealName} numberOfLines={1}>{it.food_name}</Text>
                  <Text style={styles.mealKcal}>{it.kcal.toFixed(0)} kcal</Text>
                </View>
              ))}
            </>
          ) : (
            <Text style={styles.infeasible}>{plan.data.note}</Text>
          )}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.lg },
  label: { ...typography.h3, color: colors.primary, marginTop: spacing.md, marginBottom: spacing.sm },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill,
    paddingHorizontal: 14, paddingVertical: 8, backgroundColor: colors.surface,
  },
  chipOn: { backgroundColor: colors.primaryLight, borderColor: colors.primary },
  chipText: { fontSize: 14, color: colors.textMuted },
  chipTextOn: { color: colors.primary, fontWeight: "600" },
  button: {
    backgroundColor: colors.primary, borderRadius: radius.md, padding: spacing.md,
    alignItems: "center", marginTop: spacing.lg,
  },
  buttonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  result: { marginTop: spacing.lg },
  resultHead: { ...typography.h2, color: colors.text, marginBottom: spacing.sm },
  mealItem: {
    flexDirection: "row", justifyContent: "space-between", backgroundColor: colors.surface,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginBottom: spacing.sm,
  },
  mealName: { ...typography.body, color: colors.text, flex: 1, marginRight: spacing.sm },
  mealKcal: { ...typography.body, color: colors.accent, fontWeight: "600" },
  infeasible: { ...typography.body, color: colors.warning },
});
