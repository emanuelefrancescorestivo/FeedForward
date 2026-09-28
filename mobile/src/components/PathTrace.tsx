/**
 * PathTrace
 * ---------
 * Renders the food -> nutrient -> goal reasoning chain as connected chips.
 * This is the "explainability made visible" surface that distinguishes
 * FeedForward from a calorie counter.
 */
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, radius, spacing } from "../theme";
import type { PathStep } from "../api/client";

const typeColor: Record<string, string> = {
  food: colors.primary,
  nutrient: colors.accent,
  goal: "#993C1D",
};

export function PathTrace({ steps }: { steps: PathStep[] }) {
  return (
    <View style={styles.wrap}>
      {steps.map((s, i) => (
        <React.Fragment key={s.node_id}>
          <View
            style={[
              styles.chip,
              { borderColor: typeColor[s.node_type] ?? colors.border },
            ]}
          >
            <Text style={[styles.chipText, { color: typeColor[s.node_type] ?? colors.text }]}>
              {s.name}
            </Text>
          </View>
          {i < steps.length - 1 && <Text style={styles.arrow}>→</Text>}
        </React.Fragment>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.xs },
  chip: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 4,
    backgroundColor: colors.surface,
  },
  chipText: { fontSize: 13, fontWeight: "500" },
  arrow: { color: colors.textMuted, marginHorizontal: 2, fontSize: 14 },
});
