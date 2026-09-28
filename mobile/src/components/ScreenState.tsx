/**
 * Shared loading, error, and empty states.
 * Every data screen should use this instead of a bare ActivityIndicator so a
 * failed request is distinguishable from an empty result.
 */
import React from "react";
import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet } from "react-native";
import { colors, spacing, radius, typography } from "../theme";

export function ScreenState({
  loading,
  error,
  empty,
  onRetry,
  emptyTitle = "Nothing here yet",
  emptyBody = "Try a different goal or filter.",
}: {
  loading?: boolean;
  error?: unknown;
  empty?: boolean;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyBody?: string;
}) {
  if (loading) {
    return (
      <View style={styles.wrap}>
        <ActivityIndicator color={colors.primary} />
        <Text style={styles.caption}>Loading</Text>
      </View>
    );
  }
  if (error) {
    return (
      <View style={styles.wrap}>
        <Text style={styles.title}>Couldn't reach FeedForward</Text>
        <Text style={styles.body}>Check that the API is running, then try again.</Text>
        {onRetry && (
          <TouchableOpacity style={styles.button} onPress={onRetry}>
            <Text style={styles.buttonText}>Retry</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  }
  if (empty) {
    return (
      <View style={styles.wrap}>
        <Text style={styles.title}>{emptyTitle}</Text>
        <Text style={styles.body}>{emptyBody}</Text>
      </View>
    );
  }
  return null;
}

const styles = StyleSheet.create({
  wrap: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg },
  title: { ...typography.h3, color: colors.text, textAlign: "center", marginBottom: spacing.sm },
  body: { ...typography.body, color: colors.textMuted, textAlign: "center", lineHeight: 22 },
  caption: { ...typography.caption, color: colors.textMuted, marginTop: spacing.sm },
  button: {
    marginTop: spacing.md, backgroundColor: colors.primary, borderRadius: radius.md,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm,
  },
  buttonText: { color: "#fff", fontWeight: "700" },
});
