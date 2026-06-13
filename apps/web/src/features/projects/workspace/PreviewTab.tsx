import { useEffect, useState } from 'react';

import { Button, MonoLabel } from '../../../components/primitives';
import { getFileContent, getOverview } from './api';

type Viewport = 'desktop' | 'mobile';

// Live preview of the dev or deployed app. When the project carries a url we frame the live
// site; otherwise we fall back to the generated project_preview.html from the files endpoint.
export function PreviewTab({ projectId }: { projectId: number }) {
  const [url, setUrl] = useState<string | null>(null);
  const [fallbackHtml, setFallbackHtml] = useState<string | null>(null);
  const [viewport, setViewport] = useState<Viewport>('desktop');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setReady(false);
    setUrl(null);
    setFallbackHtml(null);
    void (async () => {
      try {
        const overview = await getOverview(projectId);
        if (cancelled) return;
        if (overview.url) {
          setUrl(overview.url);
        } else {
          try {
            const file = await getFileContent(projectId, 'project_preview.html');
            if (!cancelled) setFallbackHtml(file.content);
          } catch {
            if (!cancelled) setFallbackHtml(null);
          }
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const frameClass =
    viewport === 'mobile'
      ? 'h-[640px] w-[375px] rounded-[26px] border-4 border-line'
      : 'h-[640px] w-full rounded-glass border border-line';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <MonoLabel tone="faint">viewport</MonoLabel>
          <div className="inline-flex overflow-hidden rounded-lg border border-line">
            <button
              type="button"
              aria-pressed={viewport === 'desktop'}
              onClick={() => setViewport('desktop')}
              className={`px-3 py-1 text-sm ${viewport === 'desktop' ? 'bg-accent text-black' : 'text-muted hover:text-accent'}`}
            >
              Desktop
            </button>
            <button
              type="button"
              aria-pressed={viewport === 'mobile'}
              onClick={() => setViewport('mobile')}
              className={`px-3 py-1 text-sm ${viewport === 'mobile' ? 'bg-accent text-black' : 'text-muted hover:text-accent'}`}
            >
              Mobile
            </button>
          </div>
        </div>
        {url ? (
          <a href={url} target="_blank" rel="noreferrer">
            <Button variant="outline">Open in new tab →</Button>
          </a>
        ) : null}
      </div>

      {url ? <MonoLabel tone="accent">{url}</MonoLabel> : null}

      <div className="flex justify-center rounded-glass border border-line bg-black/30 p-4">
        {!ready ? (
          <MonoLabel tone="faint">loading preview</MonoLabel>
        ) : url ? (
          <iframe title="app preview" src={url} className={`${frameClass} bg-white`} />
        ) : fallbackHtml ? (
          <iframe title="app preview" srcDoc={fallbackHtml} className={`${frameClass} bg-white`} />
        ) : (
          <div className="py-16 text-center">
            <MonoLabel tone="faint">no preview available</MonoLabel>
            <p className="mt-2 max-w-md text-sm text-muted">
              Set a project url in the overview, or run the Clarify stage to generate
              project_preview.html.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
