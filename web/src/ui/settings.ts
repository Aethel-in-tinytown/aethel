/** Presentation preferences are independent from the organism's own state. */
import { useEffect, useState } from "preact/hooks";
export type Theme = "auto" | "day" | "night";
export type Quality = "full" | "low";
export function usePresentation(asleep: boolean) {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const t = localStorage.getItem("aethel.theme");
      return t === "day" || t === "night" ? t : "auto";
    } catch {
      return "auto";
    }
  });
  const [quality, setQuality] = useState<Quality>(() => {
    try {
      return localStorage.getItem("aethel.quality") === "low" ? "low" : "full";
    } catch {
      return "full";
    }
  });
  const [reducedMotion, reduceMotion] = useState(false);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const changed = () => reduceMotion(media.matches);
    changed();
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  const night = theme === "night" || (theme === "auto" && asleep);
  useEffect(() => {
    document.documentElement.dataset.theme = night ? "night" : "day";
    document.documentElement.dataset.quality = quality;
    document.documentElement.dataset.motion = reducedMotion
      ? "reduced"
      : "full";
    try {
      localStorage.setItem("aethel.theme", theme);
      localStorage.setItem("aethel.quality", quality);
    } catch {
      /* Private browsing may disable storage; preferences still work in this tab. */
    }
  }, [night, quality, reducedMotion, theme]);
  return { theme, setTheme, quality, setQuality, night, reducedMotion };
}
