import { HoloObject } from '../../components/HoloObject';
import { HolographicBackdrop } from '../../components/HolographicBackdrop';
import { MonoLabel } from '../../components/primitives';
import { DOWNLOADS, PRIMARY_DOWNLOADS } from '../../app/downloads';
import type { PlatformDownload } from '../../app/downloads';
import { STAGES } from '../flow/stages';

// The public, unauthenticated landing surface for NexaOS. Distinct from the authed app shell:
// no sidebar, its own scroll. Orange is the only brand colour, every tone and font comes from
// the CSS variables, and motion is carried by classes that the global reduced motion rule
// neutralises (the holographic object also paints a single still frame under that preference).

// A primary call to action in the hero. An available platform is a real download link; one with
// no published installer is an inert coming soon chip, never a dead link.
function PrimaryDownload({ item }: { item: PlatformDownload }) {
  if (item.status === 'available' && item.url) {
    return (
      <a
        href={item.url}
        className="border-electric inline-flex flex-col rounded-glass border border-line bg-accent px-5 py-3 text-left text-black transition hover:bg-accent-hi"
      >
        <span className="text-sm font-semibold">Download for {item.name}</span>
        <span className="font-mono text-[0.66rem] uppercase tracking-[0.12em] opacity-80">
          {item.format} · {item.note}
        </span>
      </a>
    );
  }
  return (
    <div className="inline-flex flex-col rounded-glass border border-line bg-surface/70 px-5 py-3 text-left">
      <span className="text-sm font-semibold text-cream">{item.name}</span>
      <span className="mono-label mt-0.5 text-accent">coming soon</span>
    </div>
  );
}

// A platform card in the full downloads grid.
function DownloadTile({ item }: { item: PlatformDownload }) {
  const available = item.status === 'available' && Boolean(item.url);
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-base font-semibold text-cream">{item.name}</span>
        {available ? (
          <MonoLabel tone="accent">download</MonoLabel>
        ) : (
          <MonoLabel tone={item.emphasised ? 'accent' : 'faint'}>coming soon</MonoLabel>
        )}
      </div>
      <p className="mt-2 text-sm text-muted">{item.note}</p>
      <p className="mono-meta mt-3 text-faint">
        {item.family} · {item.format}
      </p>
    </>
  );

  const shell = [
    'border-electric block rounded-glass border bg-surface/60 p-5 text-left transition',
    available
      ? 'border-line hover:border-accent/60'
      : item.emphasised
        ? 'border-accent/40'
        : 'border-line opacity-80',
  ].join(' ');

  if (available && item.url) {
    return (
      <a href={item.url} className={shell}>
        {body}
      </a>
    );
  }
  return (
    <div className={shell} aria-disabled="true">
      {body}
    </div>
  );
}

function Section({
  id,
  label,
  title,
  children,
}: {
  id: string;
  label: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="mx-auto w-full max-w-5xl px-6 py-16">
      <MonoLabel tone="accent">{label}</MonoLabel>
      <h2 id={`${id}-title`} className="mt-2 text-2xl font-semibold text-cream sm:text-3xl">
        {title}
      </h2>
      <div className="mt-6">{children}</div>
    </section>
  );
}

export function MarketingHome({ onSignIn }: { onSignIn: () => void }) {
  return (
    <div className="scroll-themed h-full overflow-auto bg-canvas text-cream">
      {/* Top bar: wordmark and the sign-in link into the app. */}
      <header className="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-baseline gap-2">
            <span className="text-lg font-semibold tracking-tight text-cream">NexaOS</span>
            <span className="mono-label hidden sm:inline">personal ai operating system</span>
          </div>
          <button
            type="button"
            onClick={onSignIn}
            className="rounded-lg border border-accent px-4 py-1.5 text-sm font-semibold text-accent transition hover:bg-accent/10"
          >
            Sign in
          </button>
        </div>
      </header>

      {/* Hero. */}
      <section className="relative overflow-hidden border-b border-line">
        <HolographicBackdrop />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-0 overflow-hidden opacity-70"
        >
          <HoloObject variant="dashboard" />
        </div>
        <div className="relative z-10 mx-auto w-full max-w-5xl px-6 py-24">
          <MonoLabel tone="accent">capture to maintained project</MonoLabel>
          <h1 className="mt-3 max-w-2xl text-4xl font-semibold leading-tight text-cream sm:text-5xl">
            Your personal AI operating system.
          </h1>
          <p className="mt-5 max-w-xl text-base text-muted sm:text-lg">
            NexaOS turns a captured idea into a maintained project, learns what matters to you
            overnight, and decides what deserves your focus. You stay in control: nothing is built
            or remembered without your approval.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            {PRIMARY_DOWNLOADS.map((item) => (
              <PrimaryDownload key={item.key} item={item} />
            ))}
          </div>
          <p className="mono-meta mt-4 text-faint">
            iOS and Android are on the way. See all platforms below.
          </p>
        </div>
      </section>

      {/* What it is. */}
      <Section id="what" label="what it is" title="Two pillars, joined by a decide layer">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="border-electric rounded-glass border border-line bg-surface/60 p-5">
            <MonoLabel tone="accent">build</MonoLabel>
            <h3 className="mt-2 text-base font-semibold text-cream">Project Builder</h3>
            <p className="mt-2 text-sm text-muted">
              A seven stage pipeline takes a raw capture, classifies and routes it, drafts a plan,
              closes the gaps with you, and only then builds the project folder it maintains.
            </p>
          </div>
          <div className="border-electric rounded-glass border border-line bg-surface/60 p-5">
            <MonoLabel tone="accent">learn</MonoLabel>
            <h3 className="mt-2 text-base font-semibold text-cream">Dreaming</h3>
            <p className="mt-2 text-sm text-muted">
              Each night NexaOS reads the day and proposes what it might remember about you and
              about itself. Candidates wait for your approval before they enter long term memory.
            </p>
          </div>
          <div className="border-electric rounded-glass border border-line bg-surface/60 p-5">
            <MonoLabel tone="accent">decide</MonoLabel>
            <h3 className="mt-2 text-base font-semibold text-cream">Focus</h3>
            <p className="mt-2 text-sm text-muted">
              Focus ranks the day's work using what NexaOS knows, so the thing that matters most is
              the thing in front of you.
            </p>
          </div>
        </div>
      </Section>

      {/* The build to live pipeline. */}
      <Section
        id="pipeline"
        label="the build to live pipeline"
        title="From a captured idea to a maintained project"
      >
        <p className="max-w-2xl text-sm text-muted">
          Every idea moves left to right through the same seven stages. You can watch each one and
          step in at the gate before anything is promoted to a build.
        </p>
        <ol className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {STAGES.map((stage) => (
            <li
              key={stage.key}
              className="rounded-glass border border-line bg-surface/60 p-4"
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-accent">{stage.number}</span>
                <span className="text-sm font-semibold text-cream">{stage.title}</span>
              </div>
              <p className="mono-meta mt-2 text-faint">{stage.headerLabel}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* Honesty and approval model. */}
      <Section
        id="honesty"
        label="honesty and approval"
        title="You approve what gets built and what gets remembered"
      >
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-glass border border-line bg-surface/60 p-5">
            <h3 className="text-base font-semibold text-cream">A human gate</h3>
            <p className="mt-2 text-sm text-muted">
              No project is promoted to a build until you approve the plan. You can send it back
              with changes as many times as you need.
            </p>
          </div>
          <div className="rounded-glass border border-line bg-surface/60 p-5">
            <h3 className="text-base font-semibold text-cream">Nothing remembered silently</h3>
            <p className="mt-2 text-sm text-muted">
              Memory candidates from Dreaming sit in a review queue. You approve, edit, or archive
              each one; nothing enters long term memory on its own.
            </p>
          </div>
          <div className="rounded-glass border border-line bg-surface/60 p-5">
            <h3 className="text-base font-semibold text-cream">Honest by default</h3>
            <p className="mt-2 text-sm text-muted">
              Surfaces show their real state, and your provider keys stay on the server, never in
              the apps. What you see is what is actually there.
            </p>
          </div>
        </div>
      </Section>

      {/* Full downloads grid with honest per platform states. */}
      <Section id="downloads" label="get nexaos" title="Download NexaOS">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {DOWNLOADS.map((item) => (
            <DownloadTile key={item.key} item={item} />
          ))}
        </div>
        <p className="mono-meta mt-6 text-faint">
          Desktop apps install the same NexaOS you reach in the browser. Mobile apps are coming
          soon.
        </p>
      </Section>

      {/* Footer with the sign-in link into the app. */}
      <footer className="border-t border-line">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-6 py-10 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <span className="text-sm font-semibold text-cream">NexaOS</span>
            <p className="mono-meta mt-1 text-faint">Build, learn, decide. With your approval.</p>
          </div>
          <button
            type="button"
            onClick={onSignIn}
            className="self-start rounded-lg border border-accent px-4 py-1.5 text-sm font-semibold text-accent transition hover:bg-accent/10 sm:self-auto"
          >
            Sign in to NexaOS
          </button>
        </div>
      </footer>
    </div>
  );
}
