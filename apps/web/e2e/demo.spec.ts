import { expect, test } from "@playwright/test";

test("Line Fire demo: submit → staged progress → report, evidence and map layers", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Analyse" }).click();
  await page.getByRole("button", { name: /Line Fire 2024/ }).click();
  await page.getByRole("button", { name: "Run analysis" }).click();

  const progress = page.getByTestId("progress");
  await expect(progress.locator('[data-status="processing_satellite"]')).toHaveAttribute("data-state", "done", {
    timeout: 90_000,
  });
  await expect(progress.locator('[data-status="completed"]')).toHaveAttribute("data-state", "done");

  const report = page.getByTestId("report");
  await expect(report).toBeVisible();
  await expect(report.getByTestId("confidence-chip")).toBeVisible();
  await expect(report.locator('[data-section="limitations"]')).toBeVisible();

  const cards = page.getByTestId("evidence-card");
  await expect(cards.first()).toBeVisible();
  await expect(cards.first()).toContainText("Observed");
  await expect(cards.first()).toContainText("Limitations");

  const legend = page.getByTestId("legend");
  await expect(legend).toContainText("Burn severity (dNBR)");
});

test("Thompson Fire (Northern California) runs statewide", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Analyse" }).click();
  await page.getByRole("button", { name: /Thompson Fire 2024/ }).click();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByTestId("progress").locator('[data-status="completed"]')).toHaveAttribute("data-state", "done", {
    timeout: 90_000,
  });
  await expect(page.getByTestId("report").getByTestId("confidence-chip")).toHaveText("Officially reported");
  await expect(page.getByTestId("report").locator('[data-section="official"]')).toContainText("Thompson");
  await expect(page.getByTestId("legend")).toContainText("Burn severity (dNBR)");
});

test("Alexander Mountain Fire (Colorado) runs nationwide", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Analyse" }).click();
  await page.getByRole("button", { name: /Alexander Mountain Fire 2024/ }).click();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByTestId("progress").locator('[data-status="completed"]')).toHaveAttribute("data-state", "done", {
    timeout: 90_000,
  });
  await expect(page.getByTestId("report").getByTestId("confidence-chip")).toHaveText("Officially reported");
  await expect(page.getByTestId("report").locator('[data-section="official"]')).toContainText("Alexander Mountain");
});

test("no area yet: submit stays disabled", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Analyse" }).click();
  await expect(page.getByRole("button", { name: "Run analysis" })).toBeDisabled();
  await expect(page.getByText("Draw an area on the map or pick a demo area.")).toBeVisible();
});

test("Active now: pick a cluster, analyse it", async ({ page }) => {
  await page.goto("/");
  const first = page.getByTestId("activity-cluster").first();
  await expect(first).toBeVisible({ timeout: 30_000 });
  await first.click();
  await page.getByRole("button", { name: "Analyse this area" }).click();
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByTestId("progress").locator('[data-status="completed"]')).toHaveAttribute("data-state", "done", {
    timeout: 90_000,
  });
  await expect(page.getByTestId("report").getByTestId("confidence-chip")).toBeVisible();
});
