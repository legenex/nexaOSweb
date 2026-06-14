import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { initDesktop } from './app/desktop';
import './index.css';

const root = document.getElementById('root');
if (!root) throw new Error('root element not found');

async function bootstrap() {
  // Pull the API base and bearer from the desktop secure store before anything reads them.
  // App is imported dynamically so the typed Brain client (which captures the API base at
  // module load) sees the desktop API base set here, not the browser default.
  await initDesktop();
  const { default: App } = await import('./App');
  createRoot(root!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void bootstrap();
