import { test, expect } from "@playwright/test";

test("real town, nighttime preferences, filters and owner care", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page).toHaveTitle(/Watch Aethel/);
  await expect(
    page.getByRole("heading", { name: "Watch Aethel" }),
  ).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible();
  const settings = await (await page.request.get("/api/v1/config")).json();
  const status = await (await page.request.get("/api/v1/status")).json();
  expect(status.language.backend).toBe(
    process.env.AETHEL_E2E_LANGUAGE ?? "heuristic",
  );
  expect(status.language.pipeline_revision).toBe(1);
  if (status.language.backend === "nltk") {
    expect(status.language.nltk_version).toBe("3.9.2");
    expect(Object.keys(status.language.resources)).toHaveLength(3);
  }
  await expect(page.getByRole("status").first()).toContainText(
    settings.websocket_engine === "disabled" ? "polling" : "live",
  );
  await page.getByLabel("Light", { exact: true }).selectOption("night");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "night");
  await page.getByLabel("Effects", { exact: true }).selectOption("low");
  await expect(page.locator("html")).toHaveAttribute("data-quality", "low");
  await page.getByLabel("Search moments").fill("no-such-moment-ever");
  await expect(page.getByText("No moments match just yet.")).toBeVisible();
  await page.getByLabel("Search moments").fill("");
  await page.getByLabel("Owner token").fill("test-owner-token");
  await page.getByRole("button", { name: "Unlock care" }).click();
  await expect(
    page.getByRole("button", { name: "Knock on her door" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Knock on her door" }).click();
  await expect(page.getByRole("status").last()).toContainText(
    /Check-in (accepted|applied)/,
  );
  await page
    .getByLabel("A letter from home")
    .fill("A friendly note from the browser test.");
  await page.getByRole("button", { name: "Send letter", exact: true }).click();
  await expect(page.getByRole("status").last()).toContainText(
    /Letter (accepted|applied)/,
  );
  await page.getByRole("button", { name: /Stillwater, the Stoic/ }).click();
  await page.getByRole("button", { name: "Request this nature" }).click();
  await expect(page.getByRole("status").last()).toContainText(
    /Nature request (accepted|applied)/,
  );
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.getByRole("button", { name: "Lock care" }).click();
  await expect(page.getByLabel("Owner token")).toHaveValue("");
  expect(errors).toEqual([]);
});

test("network failure preserves the last real moment and recovery resumes", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();
  await context.setOffline(true);
  await expect(page.getByRole("status").first()).toContainText("reconnecting", {
    timeout: 15_000,
  });
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.getByText("demo · illustrative world")).toHaveCount(0);
  await context.setOffline(false);
  await expect(page.getByRole("status").first()).toContainText(/polling|live/, {
    timeout: 30_000,
  });
});

test("reduced motion and Canvas fallback render meaningful content", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  // Phaser falls back to Canvas when WebGL context creation is unavailable.
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      ...args: Parameters<typeof original>
    ) {
      if (String(args[0]).includes("webgl")) return null;
      return original.apply(this, args);
    } as typeof original;
  });
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "reduced");
  await expect(
    page.getByRole("heading", { name: "Her journal" }),
  ).toBeVisible();
});

test("unavailable WebSocket falls back to real HTTP data", async ({ page }) => {
  const config = await (await page.request.get("/api/v1/config")).json();
  test.skip(
    config.websocket_engine === "disabled",
    "Covered by the polling-only deployment",
  );
  await page.routeWebSocket("**/api/v1/stream", (socket) => socket.close());
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.getByRole("status").first()).toContainText("polling");
  await expect(page.getByText("demo · illustrative world")).toHaveCount(0);
});

test("failed illustration import keeps the journal available and can reload", async ({
  page,
}) => {
  await page.route("**/chunks/createGame-*.js", (route) => route.abort());
  await page.goto("/");
  await expect(
    page.getByText(
      "The town illustration could not load. Her journal is still here.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Her journal" }),
  ).toBeVisible();
  await page.unroute("**/chunks/createGame-*.js");
  await page.getByRole("button", { name: "Reload the town" }).click();
  await expect(page.locator("canvas")).toBeVisible();
});
