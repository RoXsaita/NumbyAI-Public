export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const TOTAL_FRAMES = 2189;

export const VIDEO_SRC = "/original.mp4";

export const BRAND_RED = "#DC2626";
export const BRAND_DARK = "#0F172A";
export const BRAND_WHITE = "#FFFFFF";
export const ACCENT_BLUE = "#3B82F6";
export const ACCENT_GOLD = "#F59E0B";

export interface ZoomKeyframe {
  startFrame: number;
  endFrame: number;
  scale: number;
  originX: number;
  originY: number;
  label?: string;
}

export interface CalloutLabel {
  startFrame: number;
  endFrame: number;
  text: string;
  subtext?: string;
  position: "bottom-left" | "bottom-right" | "top-left" | "top-right";
  icon?: string;
}

export const ZOOM_KEYFRAMES: ZoomKeyframe[] = [
  // Zoom into the paper budget
  { startFrame: 0, endFrame: 120, scale: 1.0, originX: 50, originY: 50 },
  // Zoom into NumbyAI bank selection
  { startFrame: 180, endFrame: 270, scale: 1.25, originX: 52, originY: 55 },
  // Zoom into upload form
  { startFrame: 300, endFrame: 420, scale: 1.2, originX: 52, originY: 55 },
  // Zoom into column detection table
  { startFrame: 450, endFrame: 600, scale: 1.15, originX: 50, originY: 45 },
  // Zoom into "Looks Good → Process" button
  { startFrame: 620, endFrame: 700, scale: 1.4, originX: 52, originY: 85 },
  // Pull back for processing view
  { startFrame: 720, endFrame: 780, scale: 1.0, originX: 50, originY: 50 },
  // Zoom into AI progress / categorization
  { startFrame: 800, endFrame: 900, scale: 1.3, originX: 38, originY: 60 },
  // Zoom into 100% completion
  { startFrame: 920, endFrame: 1000, scale: 1.35, originX: 65, originY: 30 },
  // Pull back for dashboard overview
  { startFrame: 1020, endFrame: 1080, scale: 1.0, originX: 50, originY: 50 },
  // Zoom into charts
  { startFrame: 1100, endFrame: 1200, scale: 1.2, originX: 50, originY: 55 },
  // Pull back for Review tab
  { startFrame: 1220, endFrame: 1280, scale: 1.0, originX: 50, originY: 50 },
  // Zoom into Rule Advisor AI conflict
  { startFrame: 1300, endFrame: 1400, scale: 1.3, originX: 52, originY: 55 },
  // Zoom into "All clear!" message
  { startFrame: 1420, endFrame: 1500, scale: 1.35, originX: 52, originY: 50 },
  // Pull back for Rule Advisor findings
  { startFrame: 1520, endFrame: 1580, scale: 1.0, originX: 50, originY: 50 },
  // Zoom into re-categorization suggestion
  { startFrame: 1620, endFrame: 1750, scale: 1.25, originX: 52, originY: 55 },
  // Pull back for Overview
  { startFrame: 1770, endFrame: 1830, scale: 1.0, originX: 50, originY: 50 },
  // Zoom into financial totals
  { startFrame: 1850, endFrame: 1920, scale: 1.2, originX: 50, originY: 35 },
  // Pull back for Transactions
  { startFrame: 1940, endFrame: 2000, scale: 1.0, originX: 50, originY: 50 },
  // Hold steady until end
  { startFrame: 2050, endFrame: 2189, scale: 1.0, originX: 50, originY: 50 },
];

export const CALLOUT_LABELS: CalloutLabel[] = [
  {
    startFrame: 30,
    endFrame: 140,
    text: "The Old Way",
    subtext: "Manual spreadsheets & paper budgets",
    position: "bottom-right",
    icon: "📝",
  },
  {
    startFrame: 180,
    endFrame: 290,
    text: "Select Your Bank",
    subtext: "Supports any bank format",
    position: "bottom-left",
    icon: "🏦",
  },
  {
    startFrame: 310,
    endFrame: 430,
    text: "Upload Statement",
    subtext: "CSV or Excel — drag & drop",
    position: "bottom-left",
    icon: "📄",
  },
  {
    startFrame: 460,
    endFrame: 650,
    text: "Smart Column Detection",
    subtext: "AI auto-maps your columns",
    position: "bottom-left",
    icon: "🔍",
  },
  {
    startFrame: 750,
    endFrame: 950,
    text: "AI Categorization",
    subtext: "Local LLM processes every transaction",
    position: "bottom-right",
    icon: "🤖",
  },
  {
    startFrame: 960,
    endFrame: 1060,
    text: "100% Categorized",
    subtext: "39 transactions in under 2 minutes",
    position: "bottom-right",
    icon: "✅",
  },
  {
    startFrame: 1100,
    endFrame: 1220,
    text: "Financial Insights",
    subtext: "Charts, trends & cash flow analysis",
    position: "bottom-left",
    icon: "📊",
  },
  {
    startFrame: 1280,
    endFrame: 1420,
    text: "AI Review Queue",
    subtext: "Catch conflicts & edge cases",
    position: "bottom-left",
    icon: "⚡",
  },
  {
    startFrame: 1430,
    endFrame: 1530,
    text: "All Clear!",
    subtext: "Zero manual review needed",
    position: "bottom-right",
    icon: "🎯",
  },
  {
    startFrame: 1540,
    endFrame: 1760,
    text: "Rule Advisor",
    subtext: "AI suggests categorization rules",
    position: "bottom-left",
    icon: "💡",
  },
  {
    startFrame: 1850,
    endFrame: 1950,
    text: "Complete Overview",
    subtext: "Your finances at a glance",
    position: "bottom-left",
    icon: "🏠",
  },
  {
    startFrame: 1960,
    endFrame: 2120,
    text: "All Transactions",
    subtext: "Filter, sort & manage everything",
    position: "bottom-left",
    icon: "📋",
  },
];
