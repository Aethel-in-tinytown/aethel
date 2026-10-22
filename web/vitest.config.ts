/** Keep browser scenarios separate from pure domain tests. */
import { defineConfig } from "vitest/config";
export default defineConfig({ test: { include: ["tests/**/*.test.ts"] } });
