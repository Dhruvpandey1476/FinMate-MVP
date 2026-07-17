"use client";

import { useCallback, useRef, useState, ReactNode } from "react";

/**
 * Renders children with the measured pixel width of its container.
 * Reliable replacement for Recharts' ResponsiveContainer, which renders
 * blank inside CSS grid/flex because it can't resolve its own width.
 */
export function ChartBox({
  height,
  children,
}: {
  height: number;
  children: (width: number) => ReactNode;
}) {
  const [width, setWidth] = useState(0);
  const roRef = useRef<ResizeObserver | null>(null);
  const ref = useCallback((node: HTMLDivElement | null) => {
    if (roRef.current) {
      roRef.current.disconnect();
      roRef.current = null;
    }
    if (node) {
      const ro = new ResizeObserver((entries) => setWidth(entries[0].contentRect.width));
      ro.observe(node);
      roRef.current = ro;
      setWidth(node.clientWidth);
    }
  }, []);
  return (
    <div ref={ref} style={{ width: "100%", height }}>
      {width > 0 && children(width)}
    </div>
  );
}
