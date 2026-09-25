import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
const password = "workagent-isolated-e2e-password";

test("setup, inbox, proposals, knowledge, tasks and settings", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  const initialized = (await (await request.get("/api/v1/auth/status")).json())
    .initialized;
  await page.getByLabel("Dein Passwort", { exact: true }).fill(password);
  if (!initialized) {
    await page
      .getByLabel("Einrichtungscode")
      .fill(readFileSync(resolve("../.secrets/setup_token"), "utf-8").trim());
    await page.getByRole("button", { name: "Arbeitsraum erstellen" }).click();
  } else await page.getByRole("button", { name: "Arbeitsraum öffnen" }).click();
  await expect(
    page.getByRole("heading", { name: "Dein Eingang." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Freigabe für den Oktober-Launch" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/inbox-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("heading", { name: "Freigabe für den Oktober-Launch" })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Beispieldaten");
  await page.getByRole("button", { name: "Im Arbeitschat öffnen" }).click();
  await expect(
    page.getByRole("heading", { name: "Deine Arbeitschats." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Vorschläge erstellen" }).click();
  await expect(
    page
      .locator(".proposal-card")
      .filter({ hasText: "E-Mail-Antwort" })
      .first(),
  ).toBeVisible({ timeout: 30000 });
  const proposal = page
    .locator(".proposal-card")
    .filter({ hasText: "E-Mail-Antwort" })
    .filter({ hasText: "Entwurf" })
    .first();
  await proposal
    .getByRole("button", { name: "Bearbeiten", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("textbox", { name: "Text", exact: true })
    .fill(
      "Hallo Lena, ich prüfe die offenen Punkte und melde mich morgen. Viele Grüße",
    );
  await page.getByRole("button", { name: "Entwurf speichern" }).click();
  await expect(proposal).toContainText("melde mich morgen");
  await proposal.getByRole("button", { name: "Prüfen & freigeben" }).click();
  await expect(page.getByRole("dialog")).toContainText("lena@example.com");
  await page.getByRole("button", { name: "Verbindlich freigeben" }).click();
  await expect(
    page
      .locator(".proposal-card")
      .filter({ hasText: "E-Mail-Antwort" })
      .filter({ hasText: "Simuliert" })
      .first(),
  ).toBeVisible({ timeout: 30000 });
  await page
    .getByLabel("Nachricht an den Agenten")
    .fill("Was soll ich prüfen?");
  await page.getByRole("button", { name: "Senden", exact: true }).click();
  await expect(page.locator(".chat-message.assistant").last()).toContainText(
    "Demo-Antwort",
    { timeout: 30000 },
  );
  await page.screenshot({
    path: "test-results/chat-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Wissen", exact: true }).click();
  await page.getByRole("button", { name: "Neue Notiz" }).click();
  await page
    .getByRole("dialog")
    .getByLabel("Titel", { exact: true })
    .fill("Browser-Testnotiz");
  await page
    .getByRole("textbox", { name: "Deine Notiz · Markdown", exact: true })
    .fill("# Festgehalten\n\nProjekt Bernstein benötigt eine Freigabe.");
  await page.getByRole("button", { name: "Notiz speichern" }).click();
  await expect(
    page.getByRole("heading", { name: "Browser-Testnotiz" }).first(),
  ).toBeVisible();
  await page
    .getByRole("heading", { name: "Browser-Testnotiz" })
    .first()
    .click();
  await page
    .getByRole("textbox", { name: "Deine Notiz · Markdown", exact: true })
    .fill("Geänderte Fassung für Projekt Bernstein.");
  await page.getByRole("button", { name: "Notiz speichern" }).click();
  await page.getByLabel("Alles durchsuchen").fill("Bernstein");
  await page.getByLabel("Alles durchsuchen").press("Enter");
  await expect(
    page.getByRole("heading", { name: "Suchergebnisse" }),
  ).toBeVisible();
  await expect(page.locator(".search-result").first()).toContainText(
    "Bernstein",
  );
  await page.locator(".search-result").first().click();
  await expect(
    page.getByRole("dialog").locator(".citation-focus"),
  ).toContainText("Bernstein");
  await expect(
    page.getByRole("dialog").locator(".citation-focus"),
  ).toContainText("Version");
  await page.getByRole("button", { name: "Schließen", exact: true }).click();
  await page.getByRole("button", { name: "Suche schließen" }).click();
  await page.locator("input[type=file]").setInputFiles({
    name: "Browser-Dokument.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Projekt Bernstein: Die finale Abstimmung erfolgt am Donnerstag.",
    ),
  });
  await expect(
    page.getByRole("heading", { name: "Browser-Dokument.txt" }).first(),
  ).toBeVisible();
  await expect(
    page
      .locator(".knowledge-card")
      .filter({ hasText: "Browser-Dokument.txt" })
      .first(),
  ).toContainText("Bereit", { timeout: 30000 });
  await page
    .getByRole("button", { name: /^Aufgaben/ })
    .first()
    .click();
  await page.getByRole("button", { name: "Neue Aufgabe" }).click();
  await page
    .getByRole("dialog")
    .getByLabel("Titel", { exact: true })
    .fill("Browser-Aufgabe prüfen");
  await page.getByRole("button", { name: "Entwurf speichern" }).click();
  const task = page
    .locator(".proposal-card")
    .filter({ hasText: "Browser-Aufgabe prüfen" })
    .filter({ hasText: "Entwurf" })
    .first();
  await task.getByRole("button", { name: "Prüfen & freigeben" }).click();
  await page.getByRole("button", { name: "Verbindlich freigeben" }).click();
  await expect(
    page
      .locator(".task-row")
      .filter({ hasText: "Browser-Aufgabe prüfen" })
      .first(),
  ).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Kalender", exact: true }).click();
  await page.getByRole("button", { name: "Termin vorschlagen" }).click();
  await expect(page.getByRole("dialog")).toContainText("Termin anlegen");
  await page
    .getByLabel("Betreff", { exact: true })
    .fill("Browser-Termin Berlin");
  await page.getByLabel("Beginn", { exact: true }).fill("2026-10-08T10:00");
  await page.getByLabel("Ende", { exact: true }).fill("2026-10-08T10:30");
  await page.getByRole("button", { name: "Entwurf speichern" }).click();
  const eventProposal = page
    .locator(".proposal-card")
    .filter({ hasText: "Browser-Termin Berlin" })
    .first();
  await expect(eventProposal).toBeVisible();
  const proposals = await (await page.request.get("/api/v1/proposals")).json();
  const event = proposals.find(
    (p: any) => p.payload.subject === "Browser-Termin Berlin",
  );
  expect(event.payload.start).toBe("2026-10-08T10:00:00.000+02:00");
  expect(event.status).toBe("draft");
  await page
    .getByRole("button", { name: "Einstellungen", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Microsoft 365", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Dein Agent", exact: true }).click();
  await expect(page.getByLabel("Arbeitsanweisungen")).toBeVisible();
  await page.getByRole("button", { name: "Aktivität & Betrieb" }).click();
  await expect(
    page.getByRole("heading", { name: "Hintergrundverarbeitung" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Menü", exact: true }).click();
  await page.getByRole("button", { name: /^Eingang/ }).click();
  await page.screenshot({
    path: "test-results/inbox-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});
