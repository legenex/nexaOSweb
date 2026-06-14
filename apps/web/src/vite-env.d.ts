/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  // Direct links to the desktop release artifacts published by the desktop-build workflow.
  // When unset, the marketing homepage shows an honest coming soon instead of a dead link.
  readonly VITE_DOWNLOAD_MACOS?: string;
  readonly VITE_DOWNLOAD_WINDOWS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
