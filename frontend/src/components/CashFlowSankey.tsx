import {
  ResponsiveContainer,
  Sankey,
  Tooltip,
  type SankeyLinkProps,
  type SankeyNode,
  type SankeyNodeProps,
} from "recharts";
import type { CategorySpend } from "../api/client";
import { categoryColor, CHART } from "../lib/charts";
import { currency } from "../lib/format";
import { EmptyState } from "./ui";

interface SankeyNodeDatum {
  name: string;
  color: string;
}

// Recharts copies each node datum into the layout node it hands the renderers,
// so our `color` arrives alongside the computed geometry fields.
type FlowNode = SankeyNode & SankeyNodeDatum;

function Node({ x, y, width, height, payload }: SankeyNodeProps) {
  const node = payload as FlowNode;
  const isSource = node.depth === 0;
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} rx={2} fill={node.color} />
      <text
        x={isSource ? x + width + 8 : x - 8}
        y={y + height / 2}
        textAnchor={isSource ? "start" : "end"}
        dominantBaseline="middle"
        fontSize={11}
        fill="#1b1f27"
      >
        {node.name}
      </text>
    </g>
  );
}

function Link({
  sourceX,
  targetX,
  sourceY,
  targetY,
  sourceControlX,
  targetControlX,
  linkWidth,
  payload,
}: SankeyLinkProps) {
  return (
    <path
      d={`M${sourceX},${sourceY} C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
      fill="none"
      stroke={(payload.target as FlowNode).color}
      strokeWidth={Math.max(1, linkWidth)}
      strokeOpacity={0.32}
    />
  );
}

/**
 * Cash-flow Sankey: total income flows out to each spending category, with the
 * remainder flowing to Savings — or, when spending outran income, the shortfall
 * flowing in from savings. `income` is the summed inflow for the range;
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
  if (income <= 0 && spendCats.length === 0) {
    return <EmptyState>No income or spending in this range to chart.</EmptyState>;
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
  // Spending beyond income was paid out of savings (or credit). That gap gets its
  // own source so Income never sends out more than came in, and each category
  // draws on the two sources in proportion to how much of the total each covered.
  const fromSavings = Math.max(0, totalSpend - income);
  const incomeShare = totalSpend > 0 ? (totalSpend - fromSavings) / totalSpend : 0;

  const nodes: SankeyNodeDatum[] = [];
  const links: { source: number; target: number; value: number }[] = [];
  const addNode = (name: string, color: string) => nodes.push({ name, color }) - 1;

  const incomeNode = income > 0 ? addNode("Income", CHART.positive) : null;
  const savingsNode = fromSavings > 0 ? addNode("From savings", CHART.neutral) : null;
  slices.forEach((c, i) => {
    const target = addNode(c.category, categoryColor(i));
    if (incomeNode != null) {
      links.push({ source: incomeNode, target, value: c.total * incomeShare });
    }
    if (savingsNode != null) {
      links.push({ source: savingsNode, target, value: c.total * (1 - incomeShare) });
    }
  });
  if (incomeNode != null && income > totalSpend) {
    const target = addNode("Savings", CHART.savings);
    links.push({ source: incomeNode, target, value: income - totalSpend });
  }

  return (
    <div className="chart" style={{ height: 340 }}>
      <ResponsiveContainer>
        <Sankey
          data={{ nodes, links }}
          nodePadding={26}
          nodeWidth={12}
          margin={{ top: 10, right: 90, bottom: 10, left: 70 }}
          // Render functions, not placeholder elements: recharts spreads an
          // element's SVG-valid props (targetX/targetY among them) over the
          // computed geometry, so a `<Link targetX={0} … />` placeholder would
          // end every link at (0, 0).
          node={(props) => <Node {...props} />}
          link={(props) => <Link {...props} />}
        >
          <Tooltip formatter={(v) => currency(Number(v))} />
        </Sankey>
      </ResponsiveContainer>
    </div>
  );
}
