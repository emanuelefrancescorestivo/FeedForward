/**
 * Typed API client for the FeedForward backend.
 * Mirrors the Pydantic contracts in backend/feedforward/api/models.py.
 */
import Constants from "expo-constants";

/**
 * Resolve the backend base URL.
 *
 * Priority:
 *  1. An explicit apiBaseUrl set in app.json > extra (use this for production).
 *  2. In development, the Expo dev-server host IP with port 8000 — so a phone
 *     running Expo Go reaches the backend on your computer automatically,
 *     without hand-editing an IP address. (Expo exposes the dev machine as
 *     e.g. "192.168.1.5:8081"; we swap in the backend port.)
 *  3. Fallback to localhost (works for the web/simulator, not a physical phone).
 */
function resolveBaseUrl(): string {
  const explicit = Constants.expoConfig?.extra?.apiBaseUrl as string | undefined;
  // Only trust an explicit URL if it isn't the placeholder domain.
  if (explicit && !explicit.includes("api.feedforward.app")) return explicit;

  const hostUri =
    (Constants.expoConfig as any)?.hostUri ||
    (Constants as any)?.expoGoConfig?.hostUri ||
    (Constants as any)?.manifest2?.extra?.expoClient?.hostUri;
  if (hostUri) {
    const host = String(hostUri).split(":")[0]; // strip the Metro port
    return `http://${host}:8000`;
  }
  return "http://localhost:8000";
}

const BASE_URL = resolveBaseUrl();

let authToken: string | null = null;
export function setAuthToken(token: string | null) {
  authToken = token;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ---- Types ----
export interface PathStep {
  node_id: string;
  name: string;
  node_type: string;
}
export interface Explanation {
  food_id: string;
  food_name: string;
  goal: string;
  total_cost: number;
  steps: PathStep[];
  nutrient: string;
  evidence: string;
  evidence_label: string;
  consumer_label: string;
  citations: string[];
  note: string;
}
export interface Recommendation {
  food_id: string;
  food_name: string;
  category: string;
  match: number;
  score: number;
  explanation: Explanation | null;
}
export interface Goal {
  id: string;
  label: string;
  system: string;
  description: string;
  icd10_refs: string[];
}
export interface SystemGoals {
  system: string;
  system_label: string;
  goals: Goal[];
}
export interface MealPlan {
  goal: string;
  feasible: boolean;
  total_cost: number;
  total_kcal: number;
  items: { food_id: string; food_name: string; cost: number; kcal: number }[];
  note: string;
}
export interface FoodDetail {
  food_id: string;
  food_name: string;
  category: string;
  nutri_score: string;
  nova: number;
  nutrients: Record<string, number>;
  goals_supported: { goal: string; match: number; nutrient: string; evidence: string; citations?: string[] }[];
  similar: Recommendation[];
}

// ---- Endpoints ----
export const api = {
  goalsBySystem: () => request<SystemGoals[]>("/goals/by-system"),
  goals: () => request<Goal[]>("/goals"),
  recommend: (goal: string, constraints: string[] = [], k = 10) =>
    request<{ goal: string; count: number; recommendations: Recommendation[] }>(
      "/recommend",
      { method: "POST", body: JSON.stringify({ goal, constraints, k, explain: true }) }
    ),
  mealPlan: (goal: string, maxCalories = 600, k = 3, constraints: string[] = []) =>
    request<MealPlan>("/meal-plan", {
      method: "POST",
      body: JSON.stringify({ goal, max_calories: maxCalories, k, constraints }),
    }),
  foodDetail: (foodId: string) => request<FoodDetail>(`/foods/${foodId}`),
  search: (q: string) => request<Recommendation[]>(`/search?q=${encodeURIComponent(q)}`),
  register: (email: string, password: string, tier = "consumer") =>
    request<{ access_token: string; tier: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, tier }),
    }),
  login: (email: string, password: string) => {
    const body = new URLSearchParams({ username: email, password });
    return request<{ access_token: string; tier: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });
  },
  me: () => request<UserAccount>("/auth/me"),
  updateProfile: (payload: {
    demographic?: string;
    dietary_restrictions?: string[];
    tier?: "consumer" | "professional";
  }) => request<{ access_token: string; tier: string }>("/auth/profile", {
    method: "PATCH",
    body: JSON.stringify(payload),
  }),
  exportAccount: () => request<{ user: UserAccount }>("/auth/export"),
  deleteAccount: () => request<{ deleted: boolean }>("/auth/me", { method: "DELETE" }),
};

export interface UserAccount {
  email: string;
  tier: string;
  demographic: string | null;
  dietary_restrictions: string[];
  created_at: string | null;
}

// ---- Deep analysis types ----
export interface NutrientRow {
  nutrient: string;
  amount: number;
  kind: "beneficial" | "limit";
  percent_of_need?: number;
  percent_of_limit?: number;
}
export interface Caution {
  context: string;
  severity: string;
  message: string;
  disposition: string;
  citations: string[];
}
export interface FoodProfile {
  food_id: string;
  food_name: string;
  category: string;
  nutri_score: string;
  nova: number;
  density_score: number;
  density_breakdown: {
    qualifying_sum: number;
    limiting_sum: number;
    top_contributors: [string, number][];
  };
  anti_nutrients: string[];
  is_animal_source: boolean | null;
  nutrients: NutrientRow[];
  goals_supported: { goal: string; match: number; nutrient: string; evidence: string; citations?: string[] }[];
  cautions: Caution[];
}
export interface MealAnalysis {
  foods: string[];
  minerals: Record<string, {
    raw_amount: number;
    absorbable_amount: number;
    absorption_pct: number;
    percent_of_need_absorbable: number | null;
  }>;
  total_kcal: number;
}

// ---- Deep analysis endpoints ----
export const analysis = {
  profile: (foodId: string, demographic?: string) =>
    request<FoodProfile>(
      `/analysis/profile/${foodId}${demographic ? `?demographic=${demographic}` : ""}`
    ),
  meal: (foodIds: string[], demographic?: string) =>
    request<MealAnalysis>("/analysis/meal", {
      method: "POST",
      body: JSON.stringify({ food_ids: foodIds, demographic }),
    }),
};
