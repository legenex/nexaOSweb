import { useEffect, useRef } from 'react';
import type { RefObject } from 'react';

import { useReducedMotion } from '../../app/useReducedMotion';

// A glowing curved wire connecting each card to the next, drawn in a canvas layer behind
// the cards. Accent gradient stroke, soft glow, a slow flowing dash. The active segment is
// brighter. It never renders in front of a card.
export function ConnectorLayer({
  container,
  cards,
  activeIndex,
}: {
  container: RefObject<HTMLDivElement>;
  cards: RefObject<(HTMLDivElement | null)[]>;
  activeIndex: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    const cont = container.current;
    if (!canvas || !cont) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let raf = 0;
    let dash = 0;

    function size() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas!.width = cont!.clientWidth * dpr;
      canvas!.height = cont!.clientHeight * dpr;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function draw() {
      const rect = cont!.getBoundingClientRect();
      ctx!.clearRect(0, 0, cont!.clientWidth, cont!.clientHeight);
      const els = cards.current ?? [];
      for (let i = 0; i < els.length - 1; i += 1) {
        const a = els[i];
        const b = els[i + 1];
        if (!a || !b) continue;
        const ra = a.getBoundingClientRect();
        const rb = b.getBoundingClientRect();
        const x1 = ra.right - rect.left;
        const y1 = ra.top - rect.top + ra.height * 0.2;
        const x2 = rb.left - rect.left;
        const y2 = rb.top - rect.top + rb.height * 0.2;
        const active = i === activeIndex;

        const gradient = ctx!.createLinearGradient(x1, y1, x2, y2);
        gradient.addColorStop(0, 'rgba(220, 50, 26, 0.75)');
        gradient.addColorStop(1, 'rgba(255, 115, 32, 0.95)');
        ctx!.strokeStyle = gradient;
        ctx!.lineWidth = active ? 2.4 : 1.3;
        ctx!.shadowColor = 'rgba(255, 115, 32, 0.55)';
        ctx!.shadowBlur = active ? 12 : 4;
        ctx!.setLineDash([6, 8]);
        ctx!.lineDashOffset = -dash;
        ctx!.globalAlpha = active ? 1 : 0.7;

        const mx = (x1 + x2) / 2;
        ctx!.beginPath();
        ctx!.moveTo(x1, y1);
        ctx!.bezierCurveTo(mx, y1, mx, y2, x2, y2);
        ctx!.stroke();
      }
      ctx!.setLineDash([]);
      ctx!.shadowBlur = 0;
      ctx!.globalAlpha = 1;
    }

    function sizeAndDraw() {
      size();
      draw();
    }

    sizeAndDraw();
    const observer = new ResizeObserver(sizeAndDraw);
    observer.observe(cont);
    const deck = cont.querySelector('[data-deck]');
    deck?.addEventListener('scroll', draw);
    window.addEventListener('resize', sizeAndDraw);

    if (!reduced) {
      const loop = () => {
        if (document.hidden) {
          raf = requestAnimationFrame(loop);
          return;
        }
        dash = (dash + 0.4) % 14;
        draw();
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    }

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      deck?.removeEventListener('scroll', draw);
      window.removeEventListener('resize', sizeAndDraw);
    };
  }, [reduced, activeIndex, container, cards]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none absolute inset-0 z-0"
      style={{ width: '100%', height: '100%' }}
    />
  );
}
