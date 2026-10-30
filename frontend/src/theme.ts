// Hệ thống thị giác "phòng điều khiển": nền than chì, điểm nhấn xanh chanh (khớp), san hô (sai lệch).
import { theme, type ThemeConfig } from "antd";

export const C = {
  bg: "#0a0c0f",
  panel: "#11151a",
  panel2: "#161b21",
  line: "#232b34",
  lineSoft: "#1b2229",
  text: "#e7ecef",
  muted: "#8a96a3",
  faint: "#5b6672",
  lime: "#d4ff3a",
  limeDim: "#9fbf2a",
  coral: "#ff6b4a",
  amber: "#ffb547",
  cyan: "#5ce1e6",
  violet: "#b69cff",
} as const;

export const FONT_DISPLAY = "'Bricolage Grotesque Variable', 'Be Vietnam Pro', sans-serif";
export const FONT_BODY = "'Be Vietnam Pro', system-ui, sans-serif";
export const FONT_MONO = "'JetBrains Mono Variable', ui-monospace, Consolas, monospace";

// Bảng màu biểu đồ: theo thứ tự ưu tiên, đọc rõ trên nền tối.
export const CHART = [C.lime, C.cyan, C.coral, C.amber, C.violet];

export const antdTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: C.lime,
    colorInfo: C.cyan,
    colorSuccess: "#7ee081",
    colorWarning: C.amber,
    colorError: C.coral,
    colorLink: C.lime,
    colorTextLightSolid: "#0a0c0f",
    colorBgBase: C.bg,
    colorBgLayout: "transparent",
    colorBgContainer: C.panel,
    colorBgElevated: C.panel2,
    colorBorder: C.line,
    colorBorderSecondary: C.lineSoft,
    colorText: C.text,
    colorTextSecondary: C.muted,
    colorTextTertiary: C.faint,
    fontFamily: FONT_BODY,
    fontFamilyCode: FONT_MONO,
    fontSize: 14,
    borderRadius: 4,
    borderRadiusLG: 6,
    controlHeight: 34,
    wireframe: false,
  },
  components: {
    Layout: { bodyBg: "transparent", siderBg: "transparent", headerBg: "transparent" },
    Card: { headerBg: "transparent", headerFontSize: 13, paddingLG: 20 },
    Button: { primaryShadow: "0 0 0 1px rgba(212,255,58,.25), 0 6px 24px -8px rgba(212,255,58,.55)", fontWeight: 600 },
    Table: {
      headerBg: C.panel2, headerColor: C.muted, rowHoverBg: "#182028", borderColor: C.lineSoft,
      headerSplitColor: "transparent", rowSelectedBg: "rgba(212,255,58,.06)", rowSelectedHoverBg: "rgba(212,255,58,.1)",
    },
    Tabs: { itemColor: C.muted, itemHoverColor: C.text, itemSelectedColor: C.lime, inkBarColor: C.lime, titleFontSize: 14 },
    Tag: { defaultBg: C.panel2, defaultColor: C.muted },
    Modal: { contentBg: C.panel, headerBg: C.panel },
    Statistic: { contentFontSize: 30 },
    Menu: { itemBg: "transparent" },
    Select: { optionSelectedBg: "rgba(212,255,58,.1)" },
    Progress: { defaultColor: C.lime, remainingColor: C.line },
    Descriptions: { labelBg: C.panel2 },
  },
};
