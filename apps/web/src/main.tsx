import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';
import { initDesktop } from './app/desktop';
import './index.css';

const root = document.getElementById('root');
if (!root) throw new Error('root element not found');

async function bootstrap() {
  // Pull the API base and bearer from the desktop secure store when wrapped.
  await initDesktop();
  createRoot(root!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void bootstrap();
