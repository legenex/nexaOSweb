import { useEffect, useRef } from 'react';

import { useReducedMotion } from '../app/useReducedMotion';

// A slowly rotating wireframe sphere of orange and red points and edges with depth shading
// and a slight parallax on pointer position. Kept faint and behind everything. Honors
// prefers reduced motion with a single static frame.

const POINT_COUNT = 150;
const EDGE_NEIGHBORS = 3;

interface Vec3 {
  x: number;
  y: number;
  z: number;
}

function fibonacciSphere(count: number): Vec3[] {
  const points: Vec3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i += 1) {
    const y = 1 - (i / (count - 1)) * 2;
    const radius = Math.sqrt(1 - y * y);
    const theta = golden * i;
    points.push({ x: Math.cos(theta) * radius, y, z: Math.sin(theta) * radius });
  }
  return points;
}

function nearestEdges(points: Vec3[]): Array<[number, number]> {
  const edges: Array<[number, number]> = [];
  for (let i = 0; i < points.length; i += 1) {
    const distances = points
      .map((p, j) => ({ j, d: (p.x - points[i]!.x) ** 2 + (p.y - points[i]!.y) ** 2 + (p.z - points[i]!.z) ** 2 }))
      .filter((entry) => entry.j !== i)
      .sort((a, b) => a.d - b.d)
      .slice(0, EDGE_NEIGHBORS);
    for (const entry of distances) {
      if (entry.j > i) edges.push([i, entry.j]);
    }
  }
  return edges;
}

export function HolographicSphere() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const reduced = useReducedMotion();
  const pointer = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const points = fibonacciSphere(POINT_COUNT);
    const edges = nearestEdges(points);
    let raf = 0;
    let angle = 0;

    function resize() {
      const parent = canvas!.parentElement;
      if (!parent) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas!.width = parent.clientWidth * dpr;
      canvas!.height = parent.clientHeight * dpr;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener('resize', resize);

    function onPointer(event: PointerEvent) {
      const w = window.innerWidth || 1;
      const h = window.innerHeight || 1;
      pointer.current = { x: (event.clientX / w - 0.5) * 0.6, y: (event.clientY / h - 0.5) * 0.6 };
    }
    window.addEventListener('pointermove', onPointer);

    function project(p: Vec3, rot: number, cx: number, cy: number, scale: number) {
      const cos = Math.cos(rot);
      const sin = Math.sin(rot);
      const x = p.x * cos - p.z * sin;
      const z = p.x * sin + p.z * cos;
      const y = p.y + pointer.current.y * 0.3;
      const depth = (z + 1.6) / 2.6; // 0..1 front weighting
      return { sx: cx + x * scale, sy: cy + y * scale, depth };
    }

    function frame() {
      if (!reduced && document.hidden) {
        raf = requestAnimationFrame(frame);
        return;
      }
      const parent = canvas!.parentElement;
      if (!parent) return;
      const w = parent.clientWidth;
      const h = parent.clientHeight;
      ctx!.clearRect(0, 0, w, h);
      const cx = w * 0.72 + pointer.current.x * 40;
      const cy = h * 0.4;
      const scale = Math.min(w, h) * 0.32;

      for (const [a, b] of edges) {
        const pa = project(points[a]!, angle, cx, cy, scale);
        const pb = project(points[b]!, angle, cx, cy, scale);
        const alpha = 0.04 + Math.min(pa.depth, pb.depth) * 0.16;
        ctx!.strokeStyle = `rgba(255, 90, 30, ${alpha})`;
        ctx!.lineWidth = 0.6;
        ctx!.beginPath();
        ctx!.moveTo(pa.sx, pa.sy);
        ctx!.lineTo(pb.sx, pb.sy);
        ctx!.stroke();
      }

      for (const p of points) {
        const pp = project(p, angle, cx, cy, scale);
        const radius = 0.6 + pp.depth * 1.6;
        const alpha = 0.15 + pp.depth * 0.5;
        ctx!.fillStyle = `rgba(255, ${110 + Math.floor(pp.depth * 40)}, 40, ${alpha})`;
        ctx!.beginPath();
        ctx!.arc(pp.sx, pp.sy, radius, 0, Math.PI * 2);
        ctx!.fill();
      }

      if (!reduced) {
        angle += 0.0016;
        raf = requestAnimationFrame(frame);
      }
    }

    frame();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointer);
    };
  }, [reduced]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none absolute inset-0 -z-10"
      style={{ width: '100%', height: '100%' }}
    />
  );
}
