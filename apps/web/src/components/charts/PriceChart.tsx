import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type ISeriesApi, type CandlestickData, type Time } from "lightweight-charts";

interface SupportResistance {
  support: number | null;
  resistance: number | null;
}

interface Props {
  /** OHLCV candlestick data sorted by time ascending. */
  data: Array<{
    time: string; // "YYYY-MM-DD"
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
  }>;
  /** Optional support and resistance lines to overlay. */
  levels?: SupportResistance;
  /** Chart height in pixels. */
  height?: number;
}

export function PriceChart({ data, levels, height = 400 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { color: "#111827" },
        textColor: "#9CA3AF",
      },
      grid: {
        vertLines: { color: "#1F2937" },
        horzLines: { color: "#1F2937" },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: "#374151",
      },
      timeScale: {
        borderColor: "#374151",
        timeVisible: false,
      },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#10B981",
      downColor: "#EF4444",
      borderDownColor: "#EF4444",
      borderUpColor: "#10B981",
      wickDownColor: "#EF4444",
      wickUpColor: "#10B981",
    });

    const volumeSeries = chart.addHistogramSeries({
      color: "#374151",
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [height]);

  // Update data
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || data.length === 0) return;

    const candleData: CandlestickData<Time>[] = data.map((d) => ({
      time: d.time as Time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    const volumeData = data.map((d) => ({
      time: d.time as Time,
      value: d.volume ?? 0,
      color: d.close >= d.open ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)",
    }));

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);

    // Draw S/R lines
    if (levels?.support != null) {
      candleSeriesRef.current.createPriceLine({
        price: levels.support,
        color: "#3B82F6",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "S1",
      });
    }
    if (levels?.resistance != null) {
      candleSeriesRef.current.createPriceLine({
        price: levels.resistance,
        color: "#F59E0B",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "R1",
      });
    }

    chartRef.current?.timeScale().fitContent();
  }, [data, levels]);

  return (
    <div className="overflow-hidden rounded-xl border border-gray-700">
      <div ref={containerRef} />
    </div>
  );
}
