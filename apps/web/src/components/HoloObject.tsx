import { useEffect, useRef } from 'react';

import { useReducedMotion } from '../app/useReducedMotion';

// A large, panorama grade holographic object drawn on a canvas, one distinct cyber form per
// surface. Like the backdrop sphere it is vector/GPU drawn (Canvas2D, DPR aware) so it stays
// crisp at any size, has depth and perspective, glows, rotates slowly on its own, and tilts
// toward the pointer. Colour is read from the brand CSS variables, never hardcoded. The canvas
// fills its (clipped, pointer-events-none) parent and the form is drawn large at the lower
// right. Under reduced motion it paints a single still frame with no listeners and no loop.

export type HoloVariant = 'dashboard' | 'insights' | 'research' | 'projects';

interface Vec3 {
  x: number;
  y: number;
  z: number;
}

type Rgb = [number, number, number];

// Resolve a brand colour variable to an rgb triple. The brand vars are always defined on :root;
// the numeric guard only exists so a missing var cannot throw, it is never used in practice.
function brand(name: string): Rgb {
  const raw =
    typeof window !== 'undefined'
      ? getComputedStyle(document.documentElement).getPropertyValue(name).trim()
      : '';
  const hex = raw.replace('#', '');
  if (hex.length === 3 || hex.length === 6) {
    const full =
      hex.length === 3
        ? hex
            .split('')
            .map((c) => c + c)
            .join('')
        : hex;
    const n = Number.parseInt(full, 16);
    if (!Number.isNaN(n)) return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  return [255, 138, 66];
}

const rgba = (c: Rgb, a: number): string => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a.toFixed(3)})`;
const mix = (a: Rgb, b: Rgb, t: number): Rgb => [
  Math.round(a[0] + (b[0] - a[0]) * t),
  Math.round(a[1] + (b[1] - a[1]) * t),
  Math.round(a[2] + (b[2] - a[2]) * t),
];

function norm(p: Vec3): Vec3 {
  const len = Math.hypot(p.x, p.y, p.z) || 1;
  return { x: p.x / len, y: p.y / len, z: p.z / len };
}

// A scattered constellation sphere: fibonacci points linked to their nearest neighbours.
function constellation(count: number): { verts: Vec3[]; edges: Array<[number, number]> } {
  const verts: Vec3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i += 1) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = golden * i;
    verts.push({ x: Math.cos(theta) * r, y, z: Math.sin(theta) * r });
  }
  const edges: Array<[number, number]> = [];
  for (let i = 0; i < verts.length; i += 1) {
    const near = verts
      .map((p, j) => ({
        j,
        d: (p.x - verts[i]!.x) ** 2 + (p.y - verts[i]!.y) ** 2 + (p.z - verts[i]!.z) ** 2,
      }))
      .filter((e) => e.j !== i)
      .sort((a, b) => a.d - b.d)
      .slice(0, 3);
    for (const e of near) if (e.j > i) edges.push([i, e.j]);
  }
  return { verts, edges };
}

// A frequency-2 geodesic: an icosahedron with every face split into four. A regular triangular
// lattice, clearly distinct from the scattered constellation.
function geodesic(): { verts: Vec3[]; edges: Array<[number, number]> } {
  const t = (1 + Math.sqrt(5)) / 2;
  const base: Vec3[] = (
    [
      [-1, t, 0],
      [1, t, 0],
      [-1, -t, 0],
      [1, -t, 0],
      [0, -1, t],
      [0, 1, t],
      [0, -1, -t],
      [0, 1, -t],
      [t, 0, -1],
      [t, 0, 1],
      [-t, 0, -1],
      [-t, 0, 1],
    ] as Array<[number, number, number]>
  ).map(([x, y, z]) => norm({ x, y, z }));
  const faces: Array<[number, number, number]> = [
    [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
    [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
    [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
    [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
  ];
  const verts = [...base];
  const midCache = new Map<string, number>();
  const edgeSet = new Set<string>();
  const edges: Array<[number, number]> = [];
  const key = (a: number, b: number) => (a < b ? `${a}_${b}` : `${b}_${a}`);
  const addEdge = (a: number, b: number) => {
    const k = key(a, b);
    if (!edgeSet.has(k)) {
      edgeSet.add(k);
      edges.push([a, b]);
    }
  };
  const midpoint = (a: number, b: number): number => {
    const k = key(a, b);
    const found = midCache.get(k);
    if (found !== undefined) return found;
    const va = verts[a]!;
    const vb = verts[b]!;
    const idx = verts.length;
    verts.push(norm({ x: (va.x + vb.x) / 2, y: (va.y + vb.y) / 2, z: (va.z + vb.z) / 2 }));
    midCache.set(k, idx);
    return idx;
  };
  for (const [a, b, c] of faces) {
    const ab = midpoint(a, b);
    const bc = midpoint(b, c);
    const ca = midpoint(c, a);
    for (const [x, y] of [
      [a, ab], [ab, ca], [ca, a],
      [ab, b], [b, bc], [bc, ab],
      [ca, bc], [bc, c], [c, ca],
    ] as Array<[number, number]>) {
      addEdge(x, y);
    }
  }
  return { verts, edges };
}

// A faceted crystal: a hexagonal bipyramid with internal facet diagonals.
function crystal(): { verts: Vec3[]; edges: Array<[number, number]> } {
  const ring = 6;
  const verts: Vec3[] = [
    { x: 0, y: 1.45, z: 0 },
    { x: 0, y: -1.45, z: 0 },
  ];
  for (let i = 0; i < ring; i += 1) {
    const a = (i / ring) * Math.PI * 2;
    verts.push({ x: Math.cos(a), y: 0, z: Math.sin(a) });
  }
  const edges: Array<[number, number]> = [];
  for (let i = 0; i < ring; i += 1) {
    const cur = 2 + i;
    const next = 2 + ((i + 1) % ring);
    edges.push([0, cur], [1, cur], [cur, next]);
  }
  edges.push([2, 5], [3, 6], [4, 7]);
  return { verts, edges };
}

// A drifting cloud of nodes for the neural graph; positions animate, links recompute per frame.
function cloud(count: number): Vec3[] {
  const verts: Vec3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i += 1) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = golden * i;
    const rad = 0.6 + ((i * 53) % 40) / 100; // deterministic radius variation
    verts.push({ x: Math.cos(theta) * r * rad, y: y * rad, z: Math.sin(theta) * r * rad });
  }
  return verts;
}

interface Projected {
  sx: number;
  sy: number;
  depth: number;
}

function project(p: Vec3, ry: number, rx: number, cx: number, cy: number, scale: number): Projected {
  const cosY = Math.cos(ry);
  const sinY = Math.sin(ry);
  const x1 = p.x * cosY - p.z * sinY;
  const z1 = p.x * sinY + p.z * cosY;
  const cosX = Math.cos(rx);
  const sinX = Math.sin(rx);
  const y2 = p.y * cosX - z1 * sinX;
  const z2 = p.y * sinX + z1 * cosX;
  const persp = 1 / (1 + z2 * 0.3);
  return { sx: cx + x1 * scale * persp, sy: cy + y2 * scale * persp, depth: (z2 + 1.4) / 2.8 };
}

export function HoloObject({ variant }: { variant: HoloVariant }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const accent = brand('--accent');
    const accentHi = brand('--accent-hi');
    const accentDeep = brand('--accent-deep');

    const isGeodesic = variant === 'projects';
    const isCrystal = variant === 'research';
    const isNeural = variant === 'insights';

    const geo = isGeodesic
      ? geodesic()
      : isCrystal
        ? crystal()
        : isNeural
          ? null
          : constellation(84);
    const cloudVerts = isNeural ? cloud(24) : [];

    const target = { rx: 0, ry: 0 };
    const cam = { rx: 0, ry: 0 };
    let angle = 0;
    let raf = 0;

    function resize() {
      const parent = canvas!.parentElement;
      if (!parent) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas!.width = Math.max(1, parent.clientWidth) * dpr;
      canvas!.height = Math.max(1, parent.clientHeight) * dpr;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    const ro = new ResizeObserver(resize);
    if (canvas.parentElement) ro.observe(canvas.parentElement);

    function onPointer(event: PointerEvent) {
      const w = window.innerWidth || 1;
      const h = window.innerHeight || 1;
      target.ry = (event.clientX / w - 0.5) * 0.9;
      target.rx = (event.clientY / h - 0.5) * 0.7;
    }
    if (!reduced) window.addEventListener('pointermove', onPointer);

    function draw(time: number) {
      const parent = canvas!.parentElement;
      if (!parent) return;
      const w = parent.clientWidth;
      const h = parent.clientHeight;
      ctx!.clearRect(0, 0, w, h);

      // Large, lower right, bleeding past the clipped edge.
      const cx = w * 0.78;
      const cy = h * 0.78;
      const scale = Math.min(w, h) * 0.46 || 200;

      cam.rx += (target.rx - cam.rx) * 0.05;
      cam.ry += (target.ry - cam.ry) * 0.05;
      const ry = angle + cam.ry;
      const rx = -0.35 + cam.rx;

      ctx!.lineWidth = 1;

      if (isNeural) {
        // Drift each node on its own slow orbit, then re-link by proximity every frame.
        const pts = cloudVerts.map((p, i) => ({
          x: p.x + Math.sin(time * 0.0006 + i) * 0.16,
          y: p.y + Math.cos(time * 0.0005 + i * 1.3) * 0.16,
          z: p.z + Math.sin(time * 0.0007 + i * 0.7) * 0.16,
        }));
        const proj = pts.map((p) => project(p, ry, rx, cx, cy, scale));
        for (let i = 0; i < pts.length; i += 1) {
          for (let j = i + 1; j < pts.length; j += 1) {
            const d2 =
              (pts[i]!.x - pts[j]!.x) ** 2 +
              (pts[i]!.y - pts[j]!.y) ** 2 +
              (pts[i]!.z - pts[j]!.z) ** 2;
            if (d2 < 0.62) {
              const depth = Math.min(proj[i]!.depth, proj[j]!.depth);
              ctx!.strokeStyle = rgba(mix(accentDeep, accent, depth), 0.08 + (1 - d2) * 0.22);
              ctx!.beginPath();
              ctx!.moveTo(proj[i]!.sx, proj[i]!.sy);
              ctx!.lineTo(proj[j]!.sx, proj[j]!.sy);
              ctx!.stroke();
            }
          }
        }
        ctx!.shadowBlur = 10;
        ctx!.shadowColor = rgba(accent, 0.5);
        proj.forEach((pp, i) => {
          const pulse = 0.5 + 0.5 * Math.sin(time * 0.002 + i);
          ctx!.fillStyle = rgba(mix(accent, accentHi, pp.depth), 0.3 + pp.depth * 0.45);
          ctx!.beginPath();
          ctx!.arc(pp.sx, pp.sy, 1.4 + pp.depth * 2.4 + pulse * 0.8, 0, Math.PI * 2);
          ctx!.fill();
        });
        ctx!.shadowBlur = 0;
      } else if (geo) {
        const proj = geo.verts.map((p) => project(p, ry, rx, cx, cy, scale));
        for (const [a, b] of geo.edges) {
          const depth = Math.min(proj[a]!.depth, proj[b]!.depth);
          ctx!.strokeStyle = rgba(mix(accentDeep, accent, depth), 0.06 + depth * 0.4);
          ctx!.beginPath();
          ctx!.moveTo(proj[a]!.sx, proj[a]!.sy);
          ctx!.lineTo(proj[b]!.sx, proj[b]!.sy);
          ctx!.stroke();
        }
        ctx!.shadowBlur = 8;
        ctx!.shadowColor = rgba(accent, 0.45);
        proj.forEach((pp) => {
          const r = (isCrystal ? 1.6 : 0.7) + pp.depth * (isCrystal ? 2.2 : 1.6);
          ctx!.fillStyle = rgba(mix(accent, accentHi, pp.depth), 0.25 + pp.depth * 0.5);
          ctx!.beginPath();
          ctx!.arc(pp.sx, pp.sy, r, 0, Math.PI * 2);
          ctx!.fill();
        });
        ctx!.shadowBlur = 0;

        // Research adds a slow radar sweep around the crystal's equator.
        if (isCrystal) {
          const sweep = reduced ? 0.8 : time * 0.0012;
          const tip = project(
            { x: Math.cos(sweep) * 1.5, y: 0, z: Math.sin(sweep) * 1.5 },
            ry,
            rx,
            cx,
            cy,
            scale,
          );
          const grad = ctx!.createLinearGradient(cx, cy, tip.sx, tip.sy);
          grad.addColorStop(0, rgba(accentHi, 0.5));
          grad.addColorStop(1, rgba(accent, 0));
          ctx!.strokeStyle = grad;
          ctx!.lineWidth = 1.5;
          ctx!.beginPath();
          ctx!.moveTo(cx, cy);
          ctx!.lineTo(tip.sx, tip.sy);
          ctx!.stroke();
          ctx!.lineWidth = 1;
        }
      }

      if (!reduced) {
        angle += 0.0022;
        raf = requestAnimationFrame(draw);
      }
    }

    if (reduced) {
      draw(0);
    } else {
      raf = requestAnimationFrame(draw);
    }

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener('pointermove', onPointer);
    };
  }, [variant, reduced]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none absolute inset-0 h-full w-full opacity-60"
    />
  );
}
