// Public download configuration for the marketing homepage.
//
// The desktop installers are published as GitHub release artifacts by the desktop-build
// workflow (see .github/workflows/desktop-build.yml). The marketing page links straight at
// those artifacts. Because the static web build cannot ask GitHub what has been published,
// the concrete URLs are supplied at build time through Vite env vars; until a platform's URL
// is set the page shows an honest coming soon rather than a dead link.
//
//   VITE_DOWNLOAD_MACOS    direct link to the latest .dmg
//   VITE_DOWNLOAD_WINDOWS  direct link to the latest .msi
//
// Mobile apps are not built yet, so iOS and Android are always coming soon, iOS emphasised.

export type DownloadStatus = 'available' | 'coming-soon';

export interface PlatformDownload {
  key: 'macos' | 'windows' | 'ios' | 'android';
  name: string;
  family: 'Desktop' | 'Mobile';
  format: string;
  note: string;
  url: string | null;
  status: DownloadStatus;
  emphasised: boolean;
}

// Treat blank or whitespace only env values as unset, so a misconfigured deploy degrades to
// coming soon rather than linking nowhere.
function envUrl(value: string | undefined): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
}

const macUrl = envUrl(import.meta.env.VITE_DOWNLOAD_MACOS);
const winUrl = envUrl(import.meta.env.VITE_DOWNLOAD_WINDOWS);

export const DOWNLOADS: PlatformDownload[] = [
  {
    key: 'macos',
    name: 'macOS',
    family: 'Desktop',
    format: '.dmg',
    note: 'Apple Silicon and Intel',
    url: macUrl,
    status: macUrl ? 'available' : 'coming-soon',
    emphasised: false,
  },
  {
    key: 'windows',
    name: 'Windows',
    family: 'Desktop',
    format: '.msi',
    note: 'Windows 10 and 11, 64 bit',
    url: winUrl,
    status: winUrl ? 'available' : 'coming-soon',
    emphasised: false,
  },
  {
    key: 'ios',
    name: 'iOS',
    family: 'Mobile',
    format: 'App Store',
    note: 'iPhone and iPad',
    url: null,
    status: 'coming-soon',
    emphasised: true,
  },
  {
    key: 'android',
    name: 'Android',
    family: 'Mobile',
    format: 'Google Play',
    note: 'Phones and tablets',
    url: null,
    status: 'coming-soon',
    emphasised: false,
  },
];

// The desktop installs are the primary calls to action in the hero.
export const PRIMARY_DOWNLOADS = DOWNLOADS.filter((item) => item.family === 'Desktop');
