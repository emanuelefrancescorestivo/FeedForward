/**
 * FeedForward — app root.
 * Bottom-tab navigation (Explore, Meal Planner, Profile) with a nested stack
 * for the goal -> recommendations -> food-detail drill-down.
 */
import React from "react";
import { StatusBar } from "expo-status-bar";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { useEffect } from "react";
import { ActivityIndicator, View } from "react-native";
import { GoalExplorerScreen } from "./src/screens/GoalExplorerScreen";
import { RecommendationsScreen } from "./src/screens/RecommendationsScreen";
import { FoodDetailScreen } from "./src/screens/FoodDetailScreen";
import { MealPlannerScreen } from "./src/screens/MealPlannerScreen";
import { ProfileScreen } from "./src/screens/ProfileScreen";
import { AuthScreen } from "./src/screens/AuthScreen";
import { OnboardingScreen } from "./src/screens/OnboardingScreen";
import { LegalScreen } from "./src/screens/LegalScreen";
import { useProfile } from "./src/store";
import { colors } from "./src/theme";

const queryClient = new QueryClient();
const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

function ExploreStack() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.primary },
        headerTintColor: "#fff",
        headerTitleStyle: { fontWeight: "600" },
      }}
    >
      <Stack.Screen name="Explore" component={GoalExplorerScreen}
        options={{ title: "FeedForward" }} />
      <Stack.Screen name="Recommendations" component={RecommendationsScreen}
        options={({ route }: any) => ({ title: route.params?.label ?? "Foods" })} />
      <Stack.Screen name="FoodDetail" component={FoodDetailScreen}
        options={({ route }: any) => ({ title: route.params?.name ?? "Food" })} />
      <Stack.Screen name="Legal" component={LegalScreen}
        options={({ route }: any) => ({ title: route.params?.which === "terms" ? "Terms" : "Privacy" })} />
    </Stack.Navigator>
  );
}

function Gate() {
  const hydrated = useProfile((s) => s.hydrated);
  const email = useProfile((s) => s.email);
  const demographic = useProfile((s) => s.demographic);
  const hydrate = useProfile((s) => s.hydrate);
  useEffect(() => { hydrate(); }, [hydrate]);
  if (!hydrated) {
    return <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}><ActivityIndicator color={colors.primary} /></View>;
  }
  if (!email) return <AuthScreen />;
  if (!demographic) return <OnboardingScreen />;
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
      }}
    >
      <Tab.Screen name="ExploreTab" component={ExploreStack} options={{ title: "Explore" }} />
      <Tab.Screen name="Meal Planner" component={MealPlannerScreen} />
      <Tab.Screen name="Profile" component={ProfileScreen} />
    </Tab.Navigator>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <NavigationContainer>
          <StatusBar style="light" />
          <Gate />
        </NavigationContainer>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
