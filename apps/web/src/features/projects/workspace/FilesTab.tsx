import { useEffect, useState } from 'react';

import { MonoLabel, StatusDot } from '../../../components/primitives';
import { renderMarkdown } from '../../flow/markdown';
import { getFileContent, getFiles } from './api';
import type { FilesResponse } from './api';

// The files tree from the Brain plus a content view for the selected file. Markdown files
// render through the shared renderer; everything else shows as monospace text.
export function FilesTab({ projectId }: { projectId: number }) {
  const [files, setFiles] = useState<FilesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [contentError, setContentError] = useState<string | null>(null);

  useEffect(() => {
    setFiles(null);
    setError(null);
    setSelectedPath(null);
    setContent(null);
    getFiles(projectId)
      .then(setFiles)
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  const openFile = (path: string) => {
    setSelectedPath(path);
    setContent(null);
    setContentError(null);
    getFileContent(projectId, path)
      .then((file) => setContent(file.content))
      .catch((err: Error) => setContentError(err.message));
  };

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!files) return <MonoLabel tone="faint">loading files</MonoLabel>;

  const fileNodes = files.tree.filter((node) => node.type === 'file');
  const isMarkdown = selectedPath?.endsWith('.md') ?? false;

  return (
    <div className="grid gap-4 md:grid-cols-[260px_1fr]">
      <div className="space-y-4">
        <div className="rounded-glass border border-line bg-surface/60 p-3">
          <MonoLabel tone="accent" className="mb-2 block">
            required files
          </MonoLabel>
          <ul className="space-y-1">
            {files.required_files.map((req) => (
              <li key={req.path} className="flex items-center gap-2">
                <StatusDot
                  state={req.present ? 'live' : 'pending'}
                  label={`${req.path} ${req.present ? 'present' : 'missing'}`}
                />
                <span className="font-mono text-xs text-cream">{req.path}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-glass border border-line bg-surface/60 p-3">
          <MonoLabel tone="accent" className="mb-2 block">
            files
          </MonoLabel>
          {fileNodes.length === 0 ? (
            <p className="text-xs text-muted">No files on disk yet.</p>
          ) : (
            <ul className="space-y-0.5">
              {fileNodes.map((node) => (
                <li key={node.path}>
                  <button
                    type="button"
                    onClick={() => openFile(node.path)}
                    className={`w-full truncate rounded px-2 py-1 text-left font-mono text-xs ${
                      selectedPath === node.path
                        ? 'bg-accent/15 text-accent'
                        : 'text-muted hover:text-accent'
                    }`}
                  >
                    {node.path}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="min-h-[300px] rounded-glass border border-line bg-surface/60 p-4">
        {!selectedPath ? (
          <MonoLabel tone="faint">select a file to view its content</MonoLabel>
        ) : contentError ? (
          <p className="text-sm text-danger">{contentError}</p>
        ) : content === null ? (
          <MonoLabel tone="faint">loading {selectedPath}</MonoLabel>
        ) : (
          <div>
            <MonoLabel tone="accent" className="mb-3 block">
              {selectedPath}
            </MonoLabel>
            {isMarkdown ? (
              <div>{renderMarkdown(content)}</div>
            ) : (
              <pre className="overflow-auto whitespace-pre-wrap break-words font-mono text-xs text-cream">
                {content}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
