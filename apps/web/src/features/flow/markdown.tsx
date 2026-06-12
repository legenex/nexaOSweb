import type { ReactNode } from 'react';

// A tiny markdown renderer for plan and summary text. Handles headings, bullet lists, and
// paragraphs, which is all the Brain emits. Not a general markdown engine.
export function renderMarkdown(source: string): ReactNode {
  const lines = source.split('\n');
  const blocks: ReactNode[] = [];
  let list: string[] = [];

  const flushList = (key: number) => {
    if (list.length === 0) return;
    blocks.push(
      <ul key={`ul-${key}`} className="mb-3 list-disc space-y-1 pl-5 text-sm text-muted">
        {list.map((entry, index) => (
          <li key={index}>{entry}</li>
        ))}
      </ul>,
    );
    list = [];
  };

  lines.forEach((raw, index) => {
    const line = raw.trimEnd();
    if (line.startsWith('## ')) {
      flushList(index);
      blocks.push(
        <h4 key={index} className="mono-label mb-1 mt-3 text-accent">
          {line.slice(3)}
        </h4>,
      );
    } else if (line.startsWith('# ')) {
      flushList(index);
      blocks.push(
        <h3 key={index} className="mb-2 text-lg font-semibold text-cream">
          {line.slice(2)}
        </h3>,
      );
    } else if (line.startsWith('- ')) {
      list.push(line.slice(2));
    } else if (line.trim() === '') {
      flushList(index);
    } else {
      flushList(index);
      blocks.push(
        <p key={index} className="mb-2 text-sm text-muted">
          {line}
        </p>,
      );
    }
  });
  flushList(lines.length);

  return <div>{blocks}</div>;
}
