import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Bar, VCPResult } from '../types'

interface Props {
  bars: Bar[]
  vcp: VCPResult | null
}

export function ChartViewer({ bars, vcp }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const chart = createChart(ref.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      timeScale: { timeVisible: true },
      height: 480,
    })
    chartRef.current = chart

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    })
    candle.setData(
      bars.map((b) => ({
        time: b.ts as UTCTimestamp,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    )

    if (vcp && vcp.pivot_buy_price != null) {
      candle.createPriceLine({
        price: vcp.pivot_buy_price,
        color: '#22d3ee',
        lineWidth: 2,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'Pivot',
      })
      if (vcp.stop_loss != null) {
        candle.createPriceLine({
          price: vcp.stop_loss,
          color: '#f97316',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: 'Stop',
        })
      }
      const markers = createSeriesMarkers(candle)
      markers.setMarkers(
        vcp.contractions.flatMap((c) => [
          {
            time: c.peak_ts as UTCTimestamp,
            position: 'belowBar' as const,
            color: '#22d3ee',
            shape: 'arrowDown' as const,
            text: `T${vcp.contractions.indexOf(c) + 1} peak ${c.depth_pct.toFixed(1)}%`,
          },
          {
            time: c.trough_ts as UTCTimestamp,
            position: 'aboveBar' as const,
            color: '#f97316',
            shape: 'arrowUp' as const,
            text: `trough`,
          },
        ]),
      )
    }

    return () => {
      chart.remove()
      chartRef.current = null
    }
  }, [bars, vcp])

  return <div ref={ref} className="w-full" />
}