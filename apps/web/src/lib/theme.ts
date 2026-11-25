/**
 * 테마: dark(기본)·light·contrast(고대비)·system(OS 설정 따름).
 * 선택은 localStorage에 두고(로그인 전·로그인 끔에도 유지), 로그인한 경우 계정 설정(`settings.theme`)에도 저장한다.
 * 적용은 <html data-theme>와 color-scheme. index.html의 인라인 스크립트가 첫 그리기 전에 같은 규칙으로 적용한다.
 */

import { useSyncExternalStore } from "react";

export type ThemeChoice = "dark" | "light" | "contrast" | "system";
export const THEMES: { id: ThemeChoice; label: string }[] = [
  { id: "system", label: "시스템 설정" },
  { id: "dark", label: "다크" },
  { id: "light", label: "라이트" },
  { id: "contrast", label: "고대비" },
];
export const THEME_KEY = "ai-org.theme";

const listeners = new Set<() => void>();
const media = typeof window !== "undefined" ? window.matchMedia("(prefers-color-scheme: light)") : null;

export function isTheme(v: unknown): v is ThemeChoice {
  return v === "dark" || v === "light" || v === "contrast" || v === "system";
}

export function getTheme(): ThemeChoice {
  const v = localStorage.getItem(THEME_KEY);
  return isTheme(v) ? v : "dark";
}

function resolved(choice: ThemeChoice): Exclude<ThemeChoice, "system"> {
  if (choice !== "system") return choice;
  if (window.matchMedia("(prefers-contrast: more)").matches) return "contrast";
  return media?.matches ? "light" : "dark";
}

export function applyTheme(choice: ThemeChoice = getTheme()) {
  const t = resolved(choice);
  const root = document.documentElement;
  root.dataset.theme = t;
  root.classList.toggle("dark", t !== "light");
  root.style.colorScheme = t === "light" ? "light" : "dark";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", t === "light" ? "#f6f7f9" : t === "contrast" ? "#000000" : "#0e1015");
}

export function setTheme(choice: ThemeChoice) {
  localStorage.setItem(THEME_KEY, choice);
  applyTheme(choice);
  listeners.forEach((l) => l());
}

media?.addEventListener("change", () => {
  if (getTheme() === "system") applyTheme("system");
});

export function useTheme(): ThemeChoice {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    getTheme,
  );
}
