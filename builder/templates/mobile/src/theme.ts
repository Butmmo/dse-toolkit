import { useColorScheme } from "react-native";

export const BRAND = "__COLOR__";
export const BRAND_STRONG = "__COLORSTRONG__";
export const ON_BRAND = "__ONCOLOR__";

export function useTheme() {
  const dark = useColorScheme() === "dark";
  return {
    dark,
    bg: dark ? "#0f1115" : "#ffffff",
    surface: dark ? "#181b22" : "#ffffff",
    ink: dark ? "#f2f4f8" : "#14161c",
    muted: dark ? "#9aa3b2" : "#5b6472",
    line: dark ? "#2a2f3a" : "#e5e8ee",
    tint: dark ? "#1f2430" : "__TINT__",
    brand: BRAND, brandStrong: dark ? BRAND : BRAND_STRONG, onBrand: ON_BRAND, danger: "#d92d20",
  };
}
export type Theme = ReturnType<typeof useTheme>;
