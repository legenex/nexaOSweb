// Placeholder backdrop. W2 upgrades this to a rotating wireframe sphere on a canvas with
// a reduced motion fallback. For now it is a faint warm field kept behind everything.
export function HolographicBackdrop() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 -z-10"
      style={{
        background:
          'radial-gradient(circle at 70% 25%, rgba(255,115,32,0.10), transparent 55%), radial-gradient(circle at 25% 80%, rgba(220,50,26,0.08), transparent 50%)',
      }}
    />
  );
}
