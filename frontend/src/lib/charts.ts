// Shared chart palette + axis config so every recharts instance looks cohesive.
// Calm, Monarch-style tones on a light surface.

export const CHART = {
  brand: "#4f46e5", // indigo — primary series (net worth, projections)
  positive: "#0e9f6e", // emerald — income / gains
  negative: "#e02424", // red — spending / losses
  neutral: "#64748b", // slate — secondary
  grid: "#eef0f4",
  axis: "#9aa1ac",
} as const;

// Categorical palette for donuts / multi-series breakdowns.
export const CATEGORY_COLORS = [
  "#4f46e5",
  "#0e9f6e",
  "#f59e0b",
  "#3b82f6",
  "#ec4899",
  "#14b8a6",
  "#8b5cf6",
  "#ef4444",
  "#84cc16",
  "#6b7280",
] as const;

export function categoryColor(i: number): string {
  return CATEGORY_COLORS[i % CATEGORY_COLORS.length];
}

// Shared axis tick styling.
export const AXIS_TICK = { fontSize: 11, fill: CHART.axis } as const;
