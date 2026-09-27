import { test, expect } from "@playwright/test";

test("Teams conversation loads history on demand and reveals older messages", async ({
  page,
}) => {
  const messages = Array.from({ length: 55 }, (_, index) => ({
    id: String(index),
    sender: index % 2 ? "Ich" : "Alex",
    created_at: new Date(Date.UTC(2026, 8, 27, 10, index)).toISOString(),
    body: `Nachricht ${index}`,
    incoming: index % 2 === 0,
  }));
  const item = {
    id: "teams-chat",
    kind: "chat",
    source_kind: "chat",
    source_name: "Teams",
    source_id: "teams",
    title: "Chat mit Alex",
    sender: "Alex",
    status: "new",
    body: "Nachricht 54",
    occurred_at: messages[54].created_at,
    meta: {
      teams_conversation: true,
      message_count: 55,
      latest_message: "Nachricht 54",
    },
  };
  let detailRequests = 0;
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/events")) return route.abort();
    let json: unknown = [];
    if (path.endsWith("/auth/status"))
      json = { authenticated: true, initialized: true };
    if (path.endsWith("/items")) json = [item];
    if (path.endsWith("/items/teams-chat")) {
      detailRequests++;
      json = { ...item, meta: { ...item.meta, teams_messages: messages } };
    }
    await route.fulfill({ json });
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Chat mit Alex" }),
  ).toBeVisible();
  await expect(page.getByText("55 Nachrichten", { exact: true })).toBeVisible();
  expect(detailRequests).toBe(0);
  await page.getByRole("heading", { name: "Chat mit Alex" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.locator(".teams-message")).toHaveCount(50);
  await expect(dialog.getByText("Nachricht 54", { exact: true })).toBeVisible();
  expect(detailRequests).toBe(1);
  await dialog
    .getByRole("button", { name: "Ältere Nachrichten anzeigen" })
    .click();
  await expect(dialog.locator(".teams-message")).toHaveCount(55);
  await expect(dialog.locator(".teams-message").first()).toContainText(
    "Nachricht 0",
  );
  await page.screenshot({
    path: "test-results/teams-history.png",
    fullPage: true,
  });
});
