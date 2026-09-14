import { ResponsiveContainer, Sankey, Tooltip } from "recharts";
import type { CategorySpend } from "../api/client";
import { categoryColor, CHART } from "../lib/charts";
import { currency } from "../lib/format";
import { EmptyState } from "./ui";

interface SankeyNodeDatum {
  name: string;
  color: string;
}

// Recharts passes geometry + the node payload to a custom node renderer.
interface NodeProps {
  x: number;
  y: number;
  width: number;
  height: number;
  payload: SankeyNodeDatum & { depth: number };
}

function Node({ x, y, width, height, payload }: NodeProps) {
  const isSource = payload.depth === 0;
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} rx={2} fill={payload.color} />
      <text
        x={isSource ? x + width + 8 : x - 8}
        y={y + height / 2}
        textAnchor={isSource ? "start" : "end"}
        dominantBaseline="middle"
        fontSize={11}
        fill="#1b1f27"
      >
        {payload.name}
      </text>
    </g>
  );
}

interface LinkProps {
  sourceX: number;
  targetX: number;
  sourceY: number;
  targetY: number;
  sourceControlX: number;
  targetControlX: number;
  linkWidth: number;
  index: number;
  payload: { target: SankeyNodeDatum };
}

function Link({
  sourceX,
  targetX,
  sourceY,
  targetY,
  sourceControlX,
  targetControlX,
  linkWidth,
  index,
  payload,
}: LinkProps) {
  return (
    <path
      d={`M${sourceX},${sourceY} C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
      fill="none"
      stroke={payload.target.color}
      strokeWidth={Math.max(1, linkWidth)}
      strokeOpacity={0.32}
      key={index}
    />
  );
}

/**
 * Cash-flow Sankey: total income flows out to each spending category, with the
 * remainder flowing to Savings. `income` is the summed inflow for the range;
 * `categories` is spend-by-category for the same range.
 */
export default function CashFlowSankey({
  income,
  categories,
  limit = 8,
}: {
  income: number;
  categories: CategorySpend[];
  limit?: number;
}) {
  const spendCats = categories.filter((c) => c.total > 0).sort((a, b) => b.total - a.total);
  if (income <= 0 || spendCats.length === 0) {
    return <EmptyState>Not enough income and spending in this range to chart flows.</EmptyState>;
  }

  const head = spendCats.slice(0, limit);
  const tail = spendCats.slice(limit);
  const slices = [...head];
  if (tail.length > 0) {
    slices.push({
      category: "Other",
      total: tail.reduce((s, c) => s + c.total, 0),
      count: 0,
    });
  }

  const totalSpend = slices.reduce((s, c) => s + c.total, 0);
  const savings = income - totalSpend;

  const nodes: SankeyNodeDatum[] = [{ name: "Income", color: CHART.positive }];
  const links: { source: number; target: number; value: number }[] = [];
  slices.forEach((c, i) => {
    nodes.push({ name: c.category, color: categoryColor(i) });
    links.push({ source: 0, target: nodes.length - 1, value: Math.round(c.total) });
  });
  if (savings > 0) {
    nodes.push({ name: "Savings", color: CHART.brand });
    links.push({ source: 0, target: nodes.length - 1, value: Math.round(savings) });
  }

  return (
    <div className="chart" style={{ height: 340 }}>
      <ResponsiveContainer>
        <Sankey
          data={{ nodes, links }}
          nodePadding={26}
          nodeWidth={12}
          margin={{ top: 10, right: 90, bottom: 10, left: 70 }}
          node={<Node x={0} y={0} width={0} height={0} payload={{ name: "", color: "", depth: 0 }} />}
          link={
            <Link
              sourceX={0}
              targetX={0}
              sourceY={0}
              targetY={0}
              sourceControlX={0}
              targetControlX={0}
              linkWidth={0}
              index={0}
              payload={{ target: { name: "", color: "" } }}
            />
          }
        >
          <Tooltip formatter={(v) => currency(Number(v))} />
        </Sankey>
      </ResponsiveContainer>
    </div>
  );
}
