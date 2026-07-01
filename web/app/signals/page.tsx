"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, IChartApi, ISeriesApi, LineData, LineSeries, UTCTimestamp } from "lightweight-charts";
import AuthGate from "../components/AuthGate";
import NavBar from "../components/NavBar";
import { wsPricesUrl } from "@/lib/api";

const SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];

function LiveChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const [lastPrice, setLastPrice] = useState<number | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height: 320,
      layout: { background: { color: "#09090b" }, textColor: "#a1a1aa" },
      grid: { vertLines: { color: "#27272a" }, horzLines: { color: "#27272a" } },
      timeScale: { timeVisible: true },
    });
    const series = chart.addSeries(LineSeries, { color: "#34d399", lineWidth: 2 });
    chartRef.current = chart;
    seriesRef.current = series;

    const resize = () => chart.applyOptions({ width: containerRef.current?.clientWidth });
    resize();
    window.addEventListener("resize", resize);

    return () => {
      window.removeEventListener("resize", resize);
      chart.remove();
    };
  }, []);

  useEffect(() => {
    const ws = new WebSocket(wsPricesUrl(symbol));
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setLastPrice(data.close);
      const point: LineData = { time: (Math.floor(data.timestamp / 1000)) as UTCTimestamp, value: data.close };
      seriesRef.current?.update(point);
    };
    return () => ws.close();
  }, [symbol]);

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium text-zinc-100">{symbol}</span>
        <div className="flex items-center gap-2 text-sm">
          {lastPrice != null && <span className="text-zinc-300">{lastPrice.toFixed(2)}</span>}
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-500" : "bg-zinc-600"}`} />
        </div>
      </div>
      <div ref={containerRef} />
    </div>
  );
}

function SignalsContent() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <NavBar />
      <main className="mx-auto max-w-5xl px-6 py-8">
        <h1 className="mb-2 text-lg font-semibold">Live Signals</h1>
        <p className="mb-6 text-sm text-zinc-500">
          Read-only price feed for now. Strategy signal overlays (regime, entry markers) land once the
          orchestrator loop (Phase 2) is running and emitting live signal events.
        </p>
        <div className="space-y-4">
          {SYMBOLS.map((s) => <LiveChart key={s} symbol={s} />)}
        </div>
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <SignalsContent />
    </AuthGate>
  );
}
