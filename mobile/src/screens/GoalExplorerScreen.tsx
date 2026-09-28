/**
 * GoalExplorerScreen
 * ------------------
 * The home surface. Browse the clinical goal taxonomy grouped by physiological
 * system, then tap a goal to see recommended foods.
 */
import React from "react";
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api, SystemGoals } from "../api/client";
import { colors, spacing, radius, typography } from "../theme";

export function GoalExplorerScreen({ navigation }: any) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["goals-by-system"],
    queryFn: api.goalsBySystem,
  });

  if (isLoading) return <Centered><ActivityIndicator color={colors.primary} /></Centered>;
  if (error) return (
    <Centered>
      <Text style={{ color: colors.text, marginBottom: 8 }}>Couldn't load goals.</Text>
      <TouchableOpacity onPress={() => refetch()}><Text style={{ color: colors.primary }}>Retry</Text></TouchableOpacity>
    </Centered>
  );
  if (!data || data.length === 0) return <Centered><Text>No goals returned.</Text></Centered>;

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: spacing.md }}>
      <Text style={styles.title}>What do you want to support?</Text>
      <Text style={styles.subtitle}>
        Pick a goal — we'll show foods and explain exactly why they help.
      </Text>
      {(data ?? []).filter((s) => s.goals.length > 0).map((system: SystemGoals) => (
        <View key={system.system} style={styles.systemBlock}>
          <Text style={styles.systemLabel}>{system.system_label}</Text>
          <View style={styles.goalGrid}>
            {system.goals.map((g) => (
              <TouchableOpacity
                key={g.id}
                style={styles.goalCard}
                onPress={() => navigation.navigate("Recommendations", { goal: g.id, label: g.label })}
              >
                <Text style={styles.goalLabel}>{g.label}</Text>
                <Text style={styles.goalDesc} numberOfLines={2}>{g.description}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      ))}
      <Text style={styles.disclaimer}>
        FeedForward provides nutritional information for educational purposes only
        and is not a substitute for professional medical advice.
      </Text>
    </ScrollView>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <View style={styles.centered}>{children}</View>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  centered: { flex: 1, alignItems: "center", justifyContent: "center" },
  title: { ...typography.h1, color: colors.text, marginBottom: spacing.xs },
  subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.lg },
  systemBlock: { marginBottom: spacing.lg },
  systemLabel: { ...typography.h3, color: colors.primary, marginBottom: spacing.sm },
  goalGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  goalCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    width: "47%",
  },
  goalLabel: { ...typography.h3, color: colors.text, marginBottom: 2 },
  goalDesc: { ...typography.caption, color: colors.textMuted },
  disclaimer: { ...typography.caption, color: colors.textMuted, marginTop: spacing.lg,
    fontStyle: "italic", lineHeight: 18 },
});
