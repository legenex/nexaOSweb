import { useEffect, useRef } from 'react';

import { useReducedMotion } from '../app/useReducedMotion';

// A small animated holographic wireframe object, drawn in SVG from the brand variables so it
// adds no dependency and hardcodes no colour. It slowly rotates and floats with a subtle
// pointer parallax, and sits in a page header or empty corner without blocking content
// (aria hidden, pointer-events none, kept behind the content layer by the caller). Each built
// out surface passes a different variant so its object reads as distinct. Under reduced motion
// it renders a still frame: no rotation, no float, no parallax.

export type HoloVariant = 'dashboard' | 'insights' | 'research' | 'project-builder' | 'projects';

function regularPolygon(cx: number, cy: number, r: number, sides: number, rot: number) {
  return Array.from({ length: sides }, (_, i) => {
    const a = rot + (i / sides) * Math.PI * 2;
    return { x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r };
  });
}

function pointsAttr(pts: Array<{ x: number; y: number }>): string {
  return pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
}

// Each variant returns the wireframe drawn inside the rotating group. Stroke colour is
// inherited from the .holo-svg class; the holo-gold and holo-hi classes shift accent within
// the brand palette only.
function Shape({ variant }: { variant: HoloVariant }) {
  switch (variant) {
    case 'dashboard':
      // An isometric cube.
      return (
        <>
          <polygon points="34,42 66,42 66,74 34,74" />
          <polygon points="46,30 78,30 78,62 46,62" className="holo-gold" strokeOpacity={0.75} />
          <line x1="34" y1="42" x2="46" y2="30" />
          <line x1="66" y1="42" x2="78" y2="30" />
          <line x1="66" y1="74" x2="78" y2="62" />
          <line x1="34" y1="74" x2="46" y2="62" strokeOpacity={0.5} />
        </>
      );
    case 'insights':
      // Crossed orbital rings around a core.
      return (
        <>
          <ellipse cx="50" cy="50" rx="37" ry="13" />
          <ellipse
            cx="50"
            cy="50"
            rx="37"
            ry="13"
            transform="rotate(60 50 50)"
            className="holo-gold"
            strokeOpacity={0.7}
          />
          <ellipse cx="50" cy="50" rx="37" ry="13" transform="rotate(120 50 50)" strokeOpacity={0.6} />
          <circle cx="50" cy="50" r="4" className="holo-hi" />
        </>
      );
    case 'research':
      // A faceted octahedron diamond.
      return (
        <>
          <polygon points="50,14 82,50 50,86 18,50" />
          <line x1="18" y1="50" x2="82" y2="50" strokeOpacity={0.7} />
          <line x1="50" y1="14" x2="50" y2="86" className="holo-gold" strokeOpacity={0.7} />
          <polygon points="50,14 66,50 50,86 34,50" strokeOpacity={0.5} />
        </>
      );
    case 'project-builder':
      // A stacked ziggurat of isometric tiers.
      return (
        <>
          <polygon points="22,66 50,55 78,66 50,77" />
          <polygon points="28,50 50,41 72,50 50,59" className="holo-gold" strokeOpacity={0.8} />
          <polygon points="35,34 50,27 65,34 50,41" strokeOpacity={0.7} />
          <line x1="22" y1="66" x2="28" y2="50" strokeOpacity={0.4} />
          <line x1="78" y1="66" x2="72" y2="50" strokeOpacity={0.4} />
        </>
      );
    case 'projects': {
      // A geodesic hex ball: outer hexagon, spokes to centre, and an inner hexagon.
      const outer = regularPolygon(50, 50, 36, 6, -Math.PI / 2);
      const inner = regularPolygon(50, 50, 18, 6, -Math.PI / 2);
      return (
        <>
          <polygon points={pointsAttr(outer)} />
          <polygon points={pointsAttr(inner)} className="holo-gold" strokeOpacity={0.75} />
          {outer.map((p, i) => (
            <line key={i} x1="50" y1="50" x2={p.x.toFixed(1)} y2={p.y.toFixed(1)} strokeOpacity={0.4} />
          ))}
        </>
      );
    }
    default:
      return null;
  }
}

export function HoloObject({
  variant,
  size = 132,
  className = '',
}: {
  variant: HoloVariant;
  size?: number;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    if (reduced) return;
    const el = svgRef.current;
    if (!el) return;
    function onMove(event: PointerEvent) {
      const x = (event.clientX / (window.innerWidth || 1) - 0.5) * 8;
      const y = (event.clientY / (window.innerHeight || 1) - 0.5) * 8;
      el!.style.transform = `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px)`;
    }
    window.addEventListener('pointermove', onMove);
    return () => window.removeEventListener('pointermove', onMove);
  }, [reduced]);

  return (
    <div aria-hidden className={['holo-object', className].join(' ')} style={{ width: size, height: size }}>
      <svg
        ref={svgRef}
        viewBox="0 0 100 100"
        width={size}
        height={size}
        fill="none"
        className="holo-svg holo-glow"
      >
        <g className={reduced ? undefined : 'holo-float'}>
          <g className={reduced ? undefined : 'holo-spin'}>
            <Shape variant={variant} />
          </g>
        </g>
      </svg>
    </div>
  );
}
