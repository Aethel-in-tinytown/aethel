/** TypeScript owns type checking; ESLint catches unsafe and unused expressions. */
import js from "@eslint/js";
import ts from "typescript-eslint";
export default ts.config(js.configs.recommended, ...ts.configs.recommended, {
  files: ["src/**/*.{ts,tsx}", "tests/**/*.ts"],
  languageOptions: {
    globals: {
      console: "readonly",
      document: "readonly",
      window: "readonly",
      location: "readonly",
      localStorage: "readonly",
      matchMedia: "readonly",
      fetch: "readonly",
      WebSocket: "readonly",
      crypto: "readonly",
      setTimeout: "readonly",
      clearTimeout: "readonly",
      setInterval: "readonly",
      clearInterval: "readonly",
      URL: "readonly",
      URLSearchParams: "readonly",
      AbortController: "readonly",
    },
  },
  rules: {
    "@typescript-eslint/no-unused-vars": [
      "error",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
    ],
  },
});
