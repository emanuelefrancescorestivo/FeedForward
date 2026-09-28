/**
 * RecommendationsScreen
 * ---------------------
 * Ranked foods for a chosen goal. Each card shows the match score, the
 * food -> nutrient -> goal path, and an evidence badge — the full explanation,
 * inline. Dietary filters (vegetarian, vegan, low sugar) apply live.
 */
import React, { useState } from "react";
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
} from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api, Recommendation } from "../api/client";
import { colors, spacing, radius, typography } from "../theme";
import { EvidenceBadge } from "../components/EvidenceBadge";
import { PathTrace } from "../components/PathTrace";
import { ScreenState } from "../components/ScreenState";
import { useProfile } from "../store";

const FILTERS = ["vegetarian", "vegan", "low_sugar", "high_protein", "high_fiber"];

export function RecommendationsScreen({ route, navigation }: any) {
  const { goal, label } = route.params;
  const professional = useProfile((s) => s.tier === "professional");
  const defaults = useProfile((s) => s.dietaryDefaults);
  const [active, setActive] = useState<string[]>(defaults);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["recommend", goal, active],
    queryFn: () => api.recommend(goal, active, 15),
  });

  const toggle = (f: string) =>
    setActive((a) => (a.includes(f) ? a.filter((x) => x !== f) : [...a, f]));

  return (
    <View style={styles.container}>
      <View style={styles.filterBar}>
        <FlatList
          horizontal
          data={FILTERS}
          keyExtractor={(f) => f}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: spacing.md, gap: spacing.sm }}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={[styles.filterChip, active.includes(item) && styles.filterChipOn]}
              onPress={() => toggle(item)}
            >
              <Text style={[styles.filterText, active.includes(item) && styles.filterTextOn]}>
                {item.replace("_", " ")}
              </Text>
            </TouchableOpacity>
          )}
        />
      </View>

      {isLoading || error || (data && data.recommendations.length === 0) ? (
        <ScreenState
          loading={isLoading}
          error={error}
          empty={!isLoading && !error && (data?.recommendations.length ?? 0) === 0}
          onRetry={() => refetch()}
          emptyTitle="No foods for this filter"
          emptyBody="Clear a dietary filter, or pick another goal."
        />
      ) : (
        <FlatList
          data={data?.recommendations ?? []}
          keyExtractor={(r) => r.food_id}
          contentContainerStyle={{ padding: spacing.md }}
          ListHeaderComponent={
            <Text style={styles.header}>Top foods for {label}</Text>
          }
          renderItem={({ item }: { item: Recommendation }) => (
            <TouchableOpacity
              style={styles.card}
              onPress={() => navigation.navigate("FoodDetail",
                { foodId: item.food_id, name: item.food_name })}
            >
              <View style={styles.cardHead}>
                <Text style={styles.foodName} numberOfLines={2}>{item.food_name}</Text>
                <View style={styles.matchPill}>
                  <Text style={styles.matchText}>{Math.round(item.match)}</Text>
                </View>
              </View>
              {item.explanation && (
                <>
                  <View style={{ marginVertical: spacing.sm }}>
                    <PathTrace steps={item.explanation.steps} />
                  </View>
                  <EvidenceBadge
                    evidenceGrade={item.explanation.evidence}
                    consumerLabel={item.explanation.consumer_label}
                    professional={professional}
                  />
                  {professional && item.explanation.citations.length > 0 && (
                    <Text style={styles.cite}>{item.explanation.citations.join(", ")}</Text>
                  )}
                </>
              )}
            </TouchableOpacity>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  centered: { flex: 1, alignItems: "center", justifyContent: "center" },
  filterBar: { paddingVertical: spacing.sm, borderBottomWidth: 1, borderColor: colors.border },
  filterChip: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill,
    paddingHorizontal: 12, paddingVertical: 6, backgroundColor: colors.surface,
  },
  filterChipOn: { backgroundColor: colors.primaryLight, borderColor: colors.primary },
  filterText: { fontSize: 13, color: colors.textMuted },
  filterTextOn: { color: colors.primary, fontWeight: "600" },
  header: { ...typography.h2, color: colors.text, marginBottom: spacing.md },
  card: {
    backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.border, padding: spacing.md, marginBottom: spacing.sm,
  },
  cardHead: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  foodName: { ...typography.h3, color: colors.text, flex: 1, marginRight: spacing.sm },
  matchPill: {
    backgroundColor: colors.primary, borderRadius: radius.pill,
    minWidth: 34, height: 34, alignItems: "center", justifyContent: "center",
  },
  matchText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  cite: { ...typography.caption, color: colors.accent, marginTop: spacing.xs },
});
