/**
 * Account state. The token lives in expo-secure-store so a restart stays
 * logged in. Tier comes from the token response, not a local switch — the API
 * only returns citations when the token's tier is professional.
 */
import { create } from "zustand";
import * as SecureStore from "expo-secure-store";
import { api, setAuthToken } from "./api/client";

const TOKEN_KEY = "ff_token";
const PROFILE_KEY = "ff_profile";

export interface SavedProfile {
  tier: "consumer" | "professional";
  email: string | null;
  demographic: string | null;
  dietaryDefaults: string[];
}

interface ProfileState extends SavedProfile {
  hydrated: boolean;
  hydrate: () => Promise<void>;
  login: (token: string, tier: "consumer" | "professional", email: string) => Promise<void>;
  applyProfile: (patch: Partial<SavedProfile>) => Promise<void>;
  logout: () => Promise<void>;
}

async function writeSecure(key: string, value: string | null) {
  try {
    if (value == null) await SecureStore.deleteItemAsync(key);
    else await SecureStore.setItemAsync(key, value);
  } catch {
    // expo-secure-store is unavailable on web. The in-memory store still works
    // for that session; a native build persists.
  }
}

async function readSecure(key: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(key);
  } catch {
    return null;
  }
}

export const useProfile = create<ProfileState>((set, get) => ({
  tier: "consumer",
  email: null,
  demographic: null,
  dietaryDefaults: [],
  hydrated: false,
  hydrate: async () => {
    const token = await readSecure(TOKEN_KEY);
    const raw = await readSecure(PROFILE_KEY);
    if (token) setAuthToken(token);
    let saved: Partial<SavedProfile> = {};
    if (raw) {
      try { saved = JSON.parse(raw); } catch { saved = {}; }
    }
    if (token) {
      try {
        const me = await api.me();
        saved = {
          email: me.email,
          tier: me.tier === "professional" ? "professional" : "consumer",
          demographic: me.demographic,
          dietaryDefaults: me.dietary_restrictions ?? [],
        };
      } catch {
        setAuthToken(null);
        await writeSecure(TOKEN_KEY, null);
        saved = {};
      }
    }
    set({
      tier: saved.tier ?? "consumer",
      email: saved.email ?? null,
      demographic: saved.demographic ?? null,
      dietaryDefaults: saved.dietaryDefaults ?? [],
      hydrated: true,
    });
  },
  login: async (token, tier, email) => {
    setAuthToken(token);
    await writeSecure(TOKEN_KEY, token);
    const next = { tier, email, hydrated: true };
    set(next);
    await writeSecure(PROFILE_KEY, JSON.stringify({ ...get(), ...next }));
  },
  applyProfile: async (patch) => {
    const next = { ...get(), ...patch };
    set(patch);
    await writeSecure(PROFILE_KEY, JSON.stringify({
      tier: next.tier, email: next.email, demographic: next.demographic,
      dietaryDefaults: next.dietaryDefaults,
    }));
  },
  logout: async () => {
    setAuthToken(null);
    await writeSecure(TOKEN_KEY, null);
    await writeSecure(PROFILE_KEY, null);
    set({ tier: "consumer", email: null, demographic: null, dietaryDefaults: [] });
  },
}));
