// A shared resolving surface for tabs that are designed but not built yet. Styled to the
// visual spec, orange is the only brand color, all tones come from CSS variables.
export function ComingSoon({ title, blurb }: { title: string; blurb: string }) {
  return (
    <section className="flex min-h-[320px] items-center justify-center">
      <div className="rounded-glass border border-line bg-surface/60 px-10 py-12 text-center">
        <div className="mono-label text-accent">coming soon</div>
        <h2 className="mt-3 text-2xl font-semibold text-cream">{title}</h2>
        <p className="mx-auto mt-3 max-w-sm text-sm text-muted">{blurb}</p>
        <div
          aria-hidden
          className="mx-auto mt-6 h-1 w-16 rounded-full bg-accent shadow-[0_0_18px_var(--accent)]"
        />
      </div>
    </section>
  );
}
