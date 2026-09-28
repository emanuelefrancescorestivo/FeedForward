import React from "react";
import { ScrollView, Text, StyleSheet } from "react-native";
import { PRIVACY, TERMS } from "../legal";
import { colors, spacing, typography } from "../theme";

export function LegalScreen({ route }: any) {
  const which = route.params?.which === "terms" ? "terms" : "privacy";
  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: spacing.md }}>
      <Text style={styles.title}>{which === "terms" ? "Terms" : "Privacy"}</Text>
      <Text style={styles.body}>{which === "terms" ? TERMS : PRIVACY}</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  title: { ...typography.h1, color: colors.text, marginBottom: spacing.md },
  body: { ...typography.body, color: colors.text, lineHeight: 22 },
});
