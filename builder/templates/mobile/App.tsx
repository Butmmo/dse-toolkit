import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { SafeAreaView, ScrollView, Pressable, Text, View, StyleSheet, Platform } from "react-native";
import spec from "./src/spec.json";
import type { Spec } from "./src/types";
import { useTheme } from "./src/theme";
import { Blocks } from "./src/screens";

const s = spec as Spec;

export default function App() {
  const t = useTheme();
  const [id, setId] = useState(s.screens[0].id);
  const screen = s.screens.find((x) => x.id === id) ?? s.screens[0];
  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: t.bg, paddingTop: Platform.OS === "android" ? 28 : 0 }]}>
      <StatusBar style={t.dark ? "light" : "dark"} />
      <View style={[styles.header, { borderColor: t.line }]}>
        <View style={[styles.mark, { backgroundColor: t.brand }]}><Text style={{ color: t.onBrand, fontWeight: "800" }}>{s.name.charAt(0).toUpperCase()}</Text></View>
        <Text style={[styles.title, { color: t.ink }]}>{s.name}</Text>
      </View>
      <ScrollView style={styles.fill} contentContainerStyle={{ paddingBottom: 24 }} keyboardShouldPersistTaps="handled">
        <Blocks spec={s} screen={screen} go={setId} />
      </ScrollView>
      <View style={[styles.tabs, { backgroundColor: t.surface, borderColor: t.line }]} accessibilityRole="tablist">
        {s.screens.map((x) => {
          const on = x.id === screen.id;
          return (
            <Pressable key={x.id} onPress={() => setId(x.id)} style={styles.tab} accessibilityRole="tab" accessibilityState={{ selected: on }}>
              <View style={[styles.dot, { backgroundColor: on ? t.brand : "transparent" }]} />
              <Text style={{ color: on ? t.brandStrong : t.muted, fontWeight: on ? "800" : "600", fontSize: 12 }} numberOfLines={1}>{x.title}</Text>
            </Pressable>
          );
        })}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  header: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1 },
  mark: { width: 34, height: 34, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 18, fontWeight: "800" },
  tabs: { flexDirection: "row", borderTopWidth: 1, paddingBottom: Platform.OS === "ios" ? 18 : 6, paddingTop: 6 },
  tab: { flex: 1, alignItems: "center", gap: 4, paddingVertical: 6 },
  dot: { width: 24, height: 4, borderRadius: 2 },
});
