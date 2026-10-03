import { useEffect, useState } from "react";
import { api, type Insight } from "../api/client";
import { MiniMarkdown } from "../lib/markdown";
import { Card, EmptyState } from "./ui";

// Timely kinds first: a progress note or news item is what changed since the
// reader last looked; "learn" cards are the evergreen background.
const KIND_ORDER = ["progress", "news", "learn"];
const KIND_LABEL: Record<string, string> = {
  progress: "Your progress",
  news: "News",
  learn: "Learn",
};

/** Insight timestamps are naive UTC, so pin them to UTC before formatting. */
function updatedOn(iso: string): string {
  const d = new Date(/(Z|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function InsightCard({ insight }: { insight: Insight }) {
  const [open, setOpen] = useState(false);
  const updated = updatedOn(insight.updated_at);

  return (
    <article className="insight">
      <h3 className="insight-title">{insight.title}</h3>
      {insight.summary && <p className="insight-summary">{insight.summary}</p>}

      {open && (
        <div className="insight-body">
          <MiniMarkdown text={insight.body} />
          {insight.sources.length > 0 && (
            <div className="insight-sources">
              Sources:{" "}
              {insight.sources.map((s, i) => (
                <span key={`${i}-${s.url}`}>
                  {i > 0 && " · "}
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.title}
                  </a>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="insight-foot">
        {insight.body.trim() && (
          <button className="link-plain" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            {open ? "Show less" : "Read more"}
          </button>
        )}
        {insight.origin === "ai" && (
          <span className="tag">AI-written{insight.model ? ` · ${insight.model}` : ""}</span>
        )}
        {updated && <span className="muted">Updated {updated}</span>}
      </div>
    </article>
  );
}

/**
 * Reading material for a page, served by /api/insights. What it says is data —
 * shipped YAML today, a scheduled writer later — so this component only knows
 * how to lay cards out, never what they say.
 */
export default function InsightsPanel({
  page,
  title,
  sub,
}: {
  page: string;
  title: string;
  sub?: string;
}) {
  const [insights, setInsights] = useState<Insight[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    api
      .insights(page)
      .then((rows) => live && setInsights(rows))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [page]);

  if (failed) {
    return (
      <Card title={title} sub={sub}>
        <EmptyState>Couldn’t load this reading material right now.</EmptyState>
      </Card>
    );
  }
  if (insights === null) {
    return (
      <Card title={title} sub={sub}>
        <EmptyState>Loading…</EmptyState>
      </Card>
    );
  }
  if (insights.length === 0) return null;

  const kinds = [
    ...KIND_ORDER,
    ...new Set(insights.map((i) => i.kind).filter((k) => !KIND_ORDER.includes(k))),
  ];
  const groups = kinds
    .map((kind) => ({ kind, items: insights.filter((i) => i.kind === kind) }))
    .filter((g) => g.items.length > 0);

  return (
    <Card title={title} sub={sub}>
      {groups.map((g) => (
        <section key={g.kind} className="insight-group">
          {/* A lone "Learn" heading is noise; label groups once there's a choice. */}
          {groups.length > 1 && (
            <h3 className="insight-group-title">{KIND_LABEL[g.kind] ?? g.kind}</h3>
          )}
          <div className="insight-grid">
            {g.items.map((i) => (
              <InsightCard key={i.key} insight={i} />
            ))}
          </div>
        </section>
      ))}
      <p className="insight-disclaimer">
        General information for learning, not personalized financial advice.
      </p>
    </Card>
  );
}
