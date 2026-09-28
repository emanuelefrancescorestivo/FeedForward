/**
 * First-run demographic and diet. Stored on the account, not only on the device,
 * so % of daily need and meal-plan filters follow the person.
 */
import React, { useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from "react-native";
import { api } from "../api/client";
import { useProfile } from "../store";
import { colors, spacing, radius, typography } from "../theme";

const DEMOS = [
  { id: "adult_female", label: "Adult woman, 19–50" },
  { id: "adult_male", label: "Adult man, 19–50" },
  { id: "older_female", label: "Woman, 51+" },
  { id: "older_male", label: "Man, 51+" },
  { id: "teen", label: "Teen, 14–18" },
  { id: "pregnancy", label: "Pregnancy" },
  { id: "lactation", label: "Lactation" },
];
const DIETS = [
  { id: "vegetarian", label: "Vegetarian" },
  { id: "vegan", label: "Vegan" },
  { id: "low_sugar", label: "Low sugar" },
  { id: "high_protein", label: "High protein" },
  { id: "high_fiber", label: "High fibre" },
  { id: "low_sodium", label: "Low sodium" },
];

export function OnboardingScreen() {
  const apply = useProfile((s) => s.applyProfile);
  const [demo, setDemo] = useState("adult_female");
  const [diets, setDiets] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const toggle = (id: string) =>
    setDiets((d) => (d.includes(id) ? d.filter((x) => x !== id) : [...d, id]));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.updateProfile({ demographic: demo, dietary_restrictions: diets });
      await apply({
        demographic: demo,
        dietaryDefaults: diets,
        tier: res.tier === "professional" ? "professional" : "consumer",
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save profile");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: spacing.lg }}>
      <Text style={styles.title}>Who are the numbers for?</Text>
      <Text style={styles.subtitle}>
        Reference intakes differ by group. This is a population category, not a diagnosis.
      </Text>
      {DEMOS.map((d) => (
        <TouchableOpacity key={d.id} style={[styles.chip, demo === d.id && styles.chipOn]} onPress={() => setDemo(d.id)}>
          <Text style={[styles.chipText, demo === d.id && styles.chipTextOn]}>{d.label}</Text>
        </TouchableOpacity>
      ))}
      <Text style={styles.section}>Dietary filters</Text>
      <View style={styles.wrap}>
        {DIETS.map((d) => (
          <TouchableOpacity key={d.id} style={[styles.chip, diets.includes(d.id) && styles.chipOn]} onPress={() => toggle(d.id)}>
            <Text style={[styles.chipText, diets.includes(d.id) && styles.chipTextOn]}>{d.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {error && <Text style={styles.error}>{error}</Text>}
      <TouchableOpacity style={styles.button} onPress={save} disabled={busy}>
        <Text style={styles.buttonText}>{busy ? "Saving" : "Continue"}</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  title: { ...typography.h1, color: colors.text, marginBottom: spacing.sm },
  subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.lg, lineHeight: 22 },
  section: { ...typography.h3, color: colors.primary, marginTop: spacing.lg, marginBottom: spacing.sm },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill,
    paddingHorizontal: 14, paddingVertical: 8, backgroundColor: colors.surface, marginBottom: spacing.sm,
  },
  chipOn: { backgroundColor: colors.primaryLight, borderColor: colors.primary },
  chipText: { color: colors.textMuted },
  chipTextOn: { color: colors.primary, fontWeight: "600" },
  error: { color: colors.warning, marginTop: spacing.sm },
  button: { backgroundColor: colors.primary, borderRadius: radius.md, padding: spacing.md, alignItems: "center", marginTop: spacing.lg },
  buttonText: { color: "#fff", fontWeight: "700" },
});
