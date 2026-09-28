/**
 * Login and registration. Professional tier is chosen here and stored on the
 * account. It is not a payment — see the profile screen.
 */
import React, { useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, Switch, KeyboardAvoidingView, Platform,
} from "react-native";
import { api } from "../api/client";
import { useProfile } from "../store";
import { colors, spacing, radius, typography } from "../theme";

export function AuthScreen() {
  const login = useProfile((s) => s.login);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [professional, setProfessional] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      const res = mode === "login"
        ? await api.login(email.trim(), password)
        : await api.register(email.trim(), password, professional ? "professional" : "consumer");
      await login(res.access_token, res.tier === "professional" ? "professional" : "consumer", email.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not sign in");
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <Text style={styles.title}>FeedForward</Text>
      <Text style={styles.subtitle}>
        An account keeps your demographic and diet on the server, so daily-need figures are yours — not a default.
      </Text>
      <TextInput style={styles.input} autoCapitalize="none" keyboardType="email-address"
        placeholder="Email" placeholderTextColor={colors.textMuted} value={email} onChangeText={setEmail} />
      <TextInput style={styles.input} secureTextEntry placeholder="Password"
        placeholderTextColor={colors.textMuted} value={password} onChangeText={setPassword} />
      {mode === "register" && (
        <View style={styles.row}>
          <Text style={styles.rowText}>Professional account (grades and citations)</Text>
          <Switch value={professional} onValueChange={setProfessional} trackColor={{ true: colors.primary }} />
        </View>
      )}
      {error && <Text style={styles.error}>{error}</Text>}
      <TouchableOpacity style={styles.button} onPress={submit} disabled={busy}>
        <Text style={styles.buttonText}>{busy ? "Please wait" : mode === "login" ? "Log in" : "Create account"}</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={() => setMode(mode === "login" ? "register" : "login")}>
        <Text style={styles.link}>
          {mode === "login" ? "Need an account? Register" : "Already registered? Log in"}
        </Text>
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, padding: spacing.lg, justifyContent: "center" },
  title: { ...typography.h1, color: colors.primary, marginBottom: spacing.sm },
  subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.lg, lineHeight: 22 },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm, color: colors.text,
  },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginVertical: spacing.sm },
  rowText: { ...typography.caption, color: colors.text, flex: 1, marginRight: spacing.sm },
  error: { color: colors.warning, marginBottom: spacing.sm },
  button: { backgroundColor: colors.primary, borderRadius: radius.md, padding: spacing.md, alignItems: "center" },
  buttonText: { color: "#fff", fontWeight: "700" },
  link: { ...typography.body, color: colors.primary, textAlign: "center", marginTop: spacing.lg },
});
