/**
 * Account profile. Tier is the account flag returned by the API, not a local
 * switch. Turning professional mode on reissues the token; citations only
 * appear when that token is professional.
 */
import React, { useState } from "react";
import { View, Text, Switch, StyleSheet, ScrollView, TouchableOpacity } from "react-native";
import { colors, spacing, radius, typography } from "../theme";
import { useProfile } from "../store";
import { api } from "../api/client";
import { PRIVACY, TERMS } from "../legal";

export function ProfileScreen() {
  const { tier, email, demographic, dietaryDefaults, applyProfile, logout } = useProfile();
  const isPro = tier === "professional";
  const [legal, setLegal] = useState<"privacy" | "terms" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportText, setExportText] = useState<string | null>(null);

  const setTier = async (professional: boolean) => {
    setError(null);
    try {
      const res = await api.updateProfile({ tier: professional ? "professional" : "consumer" });
      await applyProfile({ tier: res.tier === "professional" ? "professional" : "consumer" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update tier");
    }
  };

  const doExport = async () => {
    setError(null);
    try {
      const data = await api.exportAccount();
      setExportText(JSON.stringify(data.user, null, 2));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    }
  };

  const doDelete = async () => {
    setError(null);
    try {
      await api.deleteAccount();
      await logout();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: spacing.md }}>
      <Text style={styles.title}>Profile</Text>
      <Text style={styles.meta}>{email}</Text>
      <Text style={styles.meta}>Demographic: {demographic?.replace(/_/g, " ")}</Text>
      {dietaryDefaults.length > 0 && (
        <Text style={styles.meta}>Diet: {dietaryDefaults.join(", ")}</Text>
      )}

      <View style={styles.card}>
        <View style={styles.rowBetween}>
          <View style={{ flex: 1, marginRight: spacing.md }}>
            <Text style={styles.rowTitle}>Professional account</Text>
            <Text style={styles.rowDesc}>
              Shows letter grades and PubMed citations. This is an account flag, not a subscription — billing is not wired yet.
            </Text>
          </View>
          <Switch value={isPro} onValueChange={setTier} trackColor={{ true: colors.primary }} />
        </View>
      </View>

      {error && <Text style={styles.error}>{error}</Text>}

      <Text style={styles.section}>Your data</Text>
      <TouchableOpacity style={styles.card} onPress={doExport}>
        <Text style={styles.rowTitle}>Export account data</Text>
        <Text style={styles.rowDesc}>Email, demographic, and diet filters. No password hash.</Text>
      </TouchableOpacity>
      {exportText && <Text style={styles.export}>{exportText}</Text>}
      <TouchableOpacity style={styles.card} onPress={doDelete}>
        <Text style={[styles.rowTitle, { color: colors.warning }]}>Delete account</Text>
        <Text style={styles.rowDesc}>Removes the user row. This cannot be undone.</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.card} onPress={() => logout()}>
        <Text style={styles.rowTitle}>Log out</Text>
      </TouchableOpacity>

      <Text style={styles.section}>Legal</Text>
      <View style={styles.rowButtons}>
        <TouchableOpacity onPress={() => setLegal(legal === "privacy" ? null : "privacy")}>
          <Text style={styles.link}>Privacy</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => setLegal(legal === "terms" ? null : "terms")}>
          <Text style={styles.link}>Terms</Text>
        </TouchableOpacity>
      </View>
      {legal && <Text style={styles.legal}>{legal === "privacy" ? PRIVACY : TERMS}</Text>}

      <Text style={styles.disclaimer}>
        FeedForward is for educational purposes only and does not provide medical
        advice, diagnosis, or treatment. Always consult a qualified healthcare
        provider regarding your health and nutrition.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  title: { ...typography.h1, color: colors.text, marginBottom: spacing.xs },
  meta: { ...typography.caption, color: colors.textMuted, marginBottom: 2 },
  card: {
    backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.border, padding: spacing.md, marginBottom: spacing.sm, marginTop: spacing.sm,
  },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  rowTitle: { ...typography.h3, color: colors.text, marginBottom: 4 },
  rowDesc: { ...typography.caption, color: colors.textMuted, lineHeight: 18 },
  section: { ...typography.h3, color: colors.primary, marginTop: spacing.lg, marginBottom: spacing.xs },
  error: { color: colors.warning, marginTop: spacing.sm },
  export: { ...typography.caption, color: colors.text, backgroundColor: colors.surface, padding: spacing.sm },
  rowButtons: { flexDirection: "row", gap: spacing.lg, marginBottom: spacing.sm },
  link: { color: colors.primary, fontWeight: "600" },
  legal: { ...typography.caption, color: colors.text, lineHeight: 18 },
  disclaimer: { ...typography.caption, color: colors.textMuted, fontStyle: "italic",
    marginTop: spacing.lg, lineHeight: 18 },
});
