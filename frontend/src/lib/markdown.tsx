// Renders the small Markdown subset insight cards are written in: paragraphs,
// "- " bullet lists and **bold**. It builds React elements rather than HTML, so
// text from a generated card can never inject markup.
import type { ReactNode } from "react";

type Block = { kind: "p"; text: string } | { kind: "ul"; items: string[] };

function parse(text: string): Block[] {
  const blocks: Block[] = [];
  let para: string[] = [];
  let list: string[] | null = null;

  const flushPara = () => {
    if (para.length) blocks.push({ kind: "p", text: para.join(" ") });
    para = [];
  };
  const flushList = () => {
    if (list) blocks.push({ kind: "ul", items: list });
    list = null;
  };

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) {
      flushPara();
      flushList();
      continue;
    }
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (bullet) {
      flushPara();
      (list ??= []).push(bullet[1]);
    } else if (list && /^\s{2,}/.test(raw)) {
      // An indented line continues the previous bullet.
      list[list.length - 1] += ` ${line}`;
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara();
  flushList();
  return blocks;
}

function inline(text: string): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .filter(Boolean)
    .map((part, i) =>
      part.length > 4 && part.startsWith("**") && part.endsWith("**") ? (
        <strong key={i}>{part.slice(2, -2)}</strong>
      ) : (
        part
      ),
    );
}

export function MiniMarkdown({ text }: { text: string }) {
  return (
    <>
      {parse(text).map((block, i) =>
        block.kind === "p" ? (
          <p key={i}>{inline(block.text)}</p>
        ) : (
          <ul key={i}>
            {block.items.map((item, j) => (
              <li key={j}>{inline(item)}</li>
            ))}
          </ul>
        ),
      )}
    </>
  );
}
