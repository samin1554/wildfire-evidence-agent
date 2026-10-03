import { expect, test } from "@playwright/test";

test("Line Fire demo: submit → staged progress → report, evidence and map layers", async ({ page }) => {
  await page.goto("/");
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

test("an area outside the county is refused before submit", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Run analysis" })).toBeDisabled();
  await expect(page.getByText("Draw an area on the map or pick a demo area.")).toBeVisible();
});
