import { test, expect } from "@playwright/test";

// Opt in because the ordinary browser suite runs against production-built assets.
test("development React source breakpoint and source map", async ({ page }) => {
  test.skip(process.env.DEBUG_SMOKE !== "1", "Requires isolated Vite development server");
  const cdp = await page.context().newCDPSession(page);
  let script: { scriptId: string; sourceMapURL?: string } | undefined;
  cdp.on("Debugger.scriptParsed", data => {
    if (data.url.includes("/src/app/Workspace.tsx")) script = data;
  });
  await cdp.send("Debugger.enable");
  await page.goto("http://localhost:5173");
  await expect(page.getByLabel("Dein Passwort", { exact: true })).toBeVisible();
  expect(script).toBeDefined();
  const source = await cdp.send("Debugger.getScriptSource", { scriptId: script!.scriptId });
  const line = source.scriptSource.split("\n").findIndex(value => value.includes("function App()"));
  expect(line).toBeGreaterThan(-1);
  expect(script!.sourceMapURL).toContain("data:application/json");
  const breakpoint = await cdp.send("Debugger.setBreakpoint", { location: { scriptId: script!.scriptId, lineNumber: line + 1 } });
  const stopped = new Promise<any>(resolve => cdp.once("Debugger.paused", resolve));
  // Trigger an actual App component render through its hash navigation listener.
  const changed = page.evaluate(() => { location.hash = "github"; });
  const paused = await stopped;
  expect(paused.callFrames[0].functionName).toBe("App");
  await cdp.send("Debugger.removeBreakpoint", { breakpointId: breakpoint.breakpointId });
  await cdp.send("Debugger.resume");
  await changed;
  await expect(page.getByLabel("Dein Passwort", { exact: true })).toBeVisible();
});
