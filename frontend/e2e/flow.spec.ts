// Luồng chính: tạo dự án → nạp tài liệu → sinh (FakeLLM) → kiểm thử Bookstore-Lab → duyệt → áp dụng → xem diff.
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

const DOC = fs.readFileSync(
  path.resolve(here, "../../SpecLoop-Bench/apis/bookstore-lab/docs/original.md"), "utf-8");

test("tạo dự án → sinh → kiểm thử → duyệt → phiên bản mới → diff", async ({ page }) => {
  const name = `E2E Bookstore ${Date.now()}`;
  await page.goto("/projects");
  await page.getByRole("button", { name: "Tạo dự án" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByLabel("Tên dự án").fill(name);
  await dlg.getByLabel("Base URL của API cần kiểm thử").fill("http://127.0.0.1:8000/v1");
  await dlg.getByLabel("URL reset").fill("/__admin/reset");
  await dlg.getByLabel("Header reset").fill("X-Admin-Token");
  await dlg.getByLabel("Giá trị").fill("reset-me");
  await dlg.getByRole("button", { name: "Tạo" }).click();
  await expect(page.getByTestId("project-title")).toHaveText(name);

  // nạp tài liệu (dán văn bản)
  await page.getByTestId("doc-text").fill(DOC);
  await page.getByTestId("doc-submit").click();
  await expect(page.getByText(/Phân đoạn \(\d+, 8 operation\)/)).toBeVisible();

  // sinh đặc tả bằng FakeLLM
  await page.getByRole("tab", { name: "Đặc tả" }).click();
  await page.getByTestId("generate-btn").click();
  await expect(page.getByTestId("job-card")).toHaveAttribute("data-status", "succeeded", { timeout: 60000 });
  await expect(page.locator(".monaco-editor").first()).toBeVisible();
  await expect(page.getByText(/v\d+ · (generated|repaired)/).first()).toBeVisible();

  // kiểm thử API thật
  await page.getByRole("tab", { name: "Kiểm thử" }).click();
  await expect(page.getByTestId("test-base-url")).toHaveValue("http://127.0.0.1:8000/v1");
  await page.getByTestId("start-test").click();
  await expect(page.getByTestId("job-card")).toHaveAttribute("data-status", "succeeded", { timeout: 5 * 60 * 1000 });

  // duyệt đề xuất
  await page.getByRole("tab", { name: "Sai lệch & đề xuất" }).click();
  const table = page.getByTestId("proposals-table");
  await expect(table.locator("tbody tr").first()).toBeVisible();
  await table.locator("tbody tr").first().click();
  await expect(page.getByTestId("finding-detail")).toBeVisible();
  const firstAccept = table.locator('button[data-testid^="accept-"]:not([disabled])').first();
  await firstAccept.click();
  await page.getByRole("checkbox", { name: "Gồm mâu thuẫn tài liệu" }).check();
  await page.getByRole("button", { name: "Chấp nhận hàng loạt ≥ ngưỡng" }).click();
  await expect(page.getByTestId("apply-btn")).toBeEnabled();
  await page.getByTestId("apply-btn").click();

  // phiên bản mới + diff
  await expect(page.getByRole("tab", { name: "Phiên bản", selected: true })).toBeVisible();
  await expect(page.getByText(/refined-1/).first()).toBeVisible();
  await expect(page.getByTestId("diff-view").locator(".monaco-diff-editor")).toBeVisible();
  await expect(page.getByText(/Diff ngữ nghĩa \([1-9]\d* thay đổi\)/)).toBeVisible();
});
