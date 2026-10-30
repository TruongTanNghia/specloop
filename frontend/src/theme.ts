// Hệ thống thị giác "doanh nghiệp": nền sáng, bề mặt trắng, viền mảnh, xanh dương chủ đạo, IBM Plex.
import type { ThemeConfig } from "antd";

export const C = {
  canvas: "#f3f5f8",
  surface: "#ffffff",
  surface2: "#f8fafc",
  line: "#e3e8ef",
  lineSoft: "#eef1f5",
  lineStrong: "#cfd6e0",
  text: "#111827",
  text2: "#374151",
  muted: "#6b7280",
  faint: "#9aa3af",
  primary: "#0b5cd6",
  primaryHover: "#0a4fb8",
  primarySoft: "#e8f0fc",
  success: "#15803d",
  successSoft: "#e7f6ec",
  warning: "#b45309",
  warningSoft: "#fdf3e1",
  danger: "#c62828",
  dangerSoft: "#fdecec",
  teal: "#0e7490",
  tealSoft: "#e3f5f8",
  purple: "#6d28d9",
  purpleSoft: "#efe9fd",
  pink: "#be185d",
} as const;

export const FONT_BODY = "'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif";
export const FONT_DISPLAY = FONT_BODY;
export const FONT_MONO = "'IBM Plex Mono', Consolas, ui-monospace, monospace";

// Bảng màu biểu đồ: xanh chủ đạo trước, các màu phụ dịu để đọc trên nền trắng.
export const CHART = [C.primary, "#7aa7ef", "#1f9e89", "#e8a317", "#d64545"];

export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: C.primary,
    colorInfo: C.primary,
    colorSuccess: "#1e9e4a",
    colorWarning: "#d97706",
    colorError: "#d32f2f",
    colorLink: C.primary,
    colorBgLayout: C.canvas,
    colorBgContainer: C.surface,
    colorBgElevated: C.surface,
    colorBorder: C.lineStrong,
    colorBorderSecondary: C.lineSoft,
    colorText: C.text,
    colorTextSecondary: C.text2,
    colorTextTertiary: C.muted,
    colorTextQuaternary: C.faint,
    fontFamily: FONT_BODY,
    fontFamilyCode: FONT_MONO,
    fontSize: 14,
    borderRadius: 6,
    borderRadiusLG: 8,
    borderRadiusSM: 4,
    controlHeight: 34,
    boxShadow: "0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.08)",
    boxShadowSecondary: "0 8px 24px rgba(16,24,40,.12)",
    wireframe: false,
  },
  components: {
    Layout: { bodyBg: C.canvas, siderBg: C.surface, headerBg: C.surface },
    Card: { headerBg: C.surface, headerFontSize: 14, paddingLG: 20, colorBorderSecondary: C.line },
    Button: { fontWeight: 500, primaryShadow: "0 1px 2px rgba(11,92,214,.25)", defaultShadow: "0 1px 2px rgba(16,24,40,.05)" },
    Table: {
      headerBg: C.surface2, headerColor: C.text2, rowHoverBg: "#f3f7fd", borderColor: C.lineSoft,
      headerSplitColor: "transparent", rowSelectedBg: C.primarySoft, rowSelectedHoverBg: "#dce8fa", cellPaddingBlockSM: 9,
    },
    Tabs: { itemColor: C.muted, itemHoverColor: C.text, itemSelectedColor: C.primary, inkBarColor: C.primary, titleFontSize: 14, horizontalItemGutter: 28 },
    Tag: { defaultBg: C.surface2, defaultColor: C.text2 },
    Modal: { titleFontSize: 18 },
    Statistic: { contentFontSize: 28 },
    Descriptions: { labelBg: C.surface2 },
    Progress: { defaultColor: C.primary, remainingColor: C.lineSoft },
    Select: { optionSelectedBg: C.primarySoft },
    Steps: { iconSize: 28, titleLineHeight: 28 },
    Alert: { withDescriptionPadding: "14px 16px" },
  },
};
