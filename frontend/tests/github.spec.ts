import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

test("GitHub filters, comments, local status, consent and copied issue order", async ({
  page,
  context,
  request,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  const state = await (await request.get("/api/v1/auth/status")).json();
  await page
    .getByLabel("Dein Passwort", { exact: true })
    .fill("workagent-isolated-e2e-password");
  if (!state.initialized) {
    await page
      .getByLabel("Einrichtungscode")
      .fill(readFileSync(resolve("../.secrets/setup_token"), "utf8").trim());
    await page.getByRole("button", { name: "Arbeitsraum erstellen" }).click();
  } else await page.getByRole("button", { name: "Arbeitsraum öffnen" }).click();
  await expect(
    page.getByRole("heading", { name: "Dein Eingang." }),
  ).toBeVisible();
  // Reset only marked demo repositories in this isolated acceptance database.
  const auth = await (await page.request.get("/api/v1/auth/status")).json();
  const repos = await (
    await page.request.get("/api/v1/github/repositories")
  ).json();
  for (const repo of repos.filter((r: any) => r.demo)) {
    await page.request.patch(`/api/v1/github/repositories/${repo.id}`, {
      data: { enabled: true, ai_enabled: false },
      headers: { "X-CSRF-Token": auth.csrf },
    });
  }
  await page.getByRole("button", { name: "GitHub", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "GitHub", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".github-issue")).toHaveCount(2);
  await page
    .getByLabel("Eigentümer", { exact: true })
    .selectOption("demo-team");
  await page
    .getByLabel("Repository", { exact: true })
    .selectOption({ label: "demo-team/work-agent" });
  await page.getByLabel("Label", { exact: true }).fill("bug");
  await page.getByLabel("Zuständig", { exact: true }).fill("sam-demo");
  await expect(page.locator(".github-issue")).toHaveCount(1);
  await page.locator(".github-issue").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Reproduziert");
  await expect(dialog).toContainText("Verknüpfte Pull Requests");
  await expect(dialog).toContainText("Nur lokal");
  await dialog.getByRole("button", { name: "Codex-Auftrag kopieren" }).click();
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe("fix issue demo-team/work-agent#42");
  await dialog.getByLabel("Lokale Bearbeitung").selectOption("in_progress");
  await expect(dialog).toContainText("GitHub: Offen");
  await page.screenshot({
    path: "test-results/github-detail.png",
    fullPage: true,
  });
  await dialog.getByRole("button", { name: "Arbeitschat öffnen" }).click();
  await expect(
    page.getByRole("heading", { name: "Deine Arbeitschats." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "GitHub", exact: true }).click();
  await page.getByLabel("GitHub-Status").selectOption("closed");
  await expect(page.locator(".github-issue")).toHaveCount(2);
  await page.getByLabel("GitHub-Status").selectOption("open");
  await page.locator(".github-repositories summary").click();
  const repo = page
    .locator(".github-repo")
    .filter({ hasText: "demo-team/work-agent" });
  await expect(repo.getByLabel("KI-Verarbeitung erlauben")).not.toBeChecked();
  await repo.getByLabel("Repository überwachen").uncheck();
  await expect(page.locator(".github-issue")).toHaveCount(1);
  await repo.getByLabel("Repository überwachen").check();
  await expect(page.locator(".github-issue")).toHaveCount(2);
  await page.screenshot({
    path: "test-results/github-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "GitHub", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/github-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
});
