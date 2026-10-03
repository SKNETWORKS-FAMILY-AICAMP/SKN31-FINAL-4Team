/* 할인률 화면 전용 가격 차트 — 실제 관측일만 그린다. */
const won = value => Math.round(value).toLocaleString('ko-KR') + '원';
const shortDate = value => value.slice(5).replace('-', '/');

export function paintStockPriceChart(host, rows) {
  if (!host) return;
  const byDay = new Map();
  for (const row of rows || []) {
    const date = String(row?.date || '').slice(0, 10);
    const sale = Number(row?.sale_price);
    const list = row?.list_price == null ? null : Number(row.list_price);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(sale) || sale <= 0) continue;
    byDay.set(date, { date, sale, list: Number.isFinite(list) && list > 0 ? list : null });
  }
  const points = [...byDay.values()].sort((a, b) => a.date.localeCompare(b.date));
  if (points.length < 2) {
    host.innerHTML = '<p class="stockHistoryEmpty">가격이 기록된 날짜가 하루뿐이라 추이를 그리지 않습니다.<br>관측값이 더 쌓이면 여기서 비교할 수 있습니다.</p>';
    return;
  }

  /* ★ 실제 폭으로 그린다 (2026-10-02) — 760 고정 viewBox 를 늘리면 큰 모니터에서 축 글씨가
     부풀고 번졌다(chart_engine.gPaint 와 같은 이유). 폭을 못 재면 예전 값으로 그려 늘린다. */
  const live = Math.round(host.clientWidth || 0);
  const width = live >= 280 ? live : 760;
  const height = live >= 280 ? Math.round(Math.min(330, Math.max(240, width * .34))) : 280;
  const left = 68, right = 18, top = 22, bottom = 38;
  host._spRows = rows; host._spW = live >= 280 ? width : 0;
  if (!host._spRO && typeof ResizeObserver !== 'undefined') {
    host._spRO = new ResizeObserver(() => {
      const w = Math.round(host.clientWidth || 0);
      if (w < 280 || Math.abs(w - (host._spW || 0)) <= 4) return;
      cancelAnimationFrame(host._spRaf);
      host._spRaf = requestAnimationFrame(() => { if (host.isConnected) paintStockPriceChart(host, host._spRows); });
    });
    host._spRO.observe(host);
  }
  const times = points.map(point => Date.parse(point.date + 'T00:00:00Z'));
  const from = times[0], span = times[times.length - 1] - from || 1;
  const values = points.flatMap(point => point.list == null ? [point.sale] : [point.sale, point.list]);
  const lo = Math.min(...values), hi = Math.max(...values);
  const rough = Math.max(1, (hi - lo) / 4);
  const scale = 10 ** Math.floor(Math.log10(rough));
  const tick = ([1, 2, 5, 10].find(n => n * scale >= rough) || 10) * scale;
  const floor = Math.max(0, Math.floor((lo - tick * .35) / tick) * tick);
  const ceil = Math.ceil((hi + tick * .35) / tick) * tick;
  const x = time => left + (time - from) / span * (width - left - right);
  const y = price => top + (ceil - price) / (ceil - floor || 1) * (height - top - bottom);
  const line = field => {
    const selected = points.map((point, i) => ({ ...point, time: times[i] }))
      .filter(point => point[field] != null);
    return selected.map((point, i) => {
      const px = x(point.time).toFixed(1), py = y(point[field]).toFixed(1);
      return i ? ` H ${px} V ${py}` : `M ${px} ${py}`;
    }).join('');
  };
  const grid = Array.from({ length: 5 }, (_, i) => {
    const value = floor + (ceil - floor) * i / 4, py = y(value).toFixed(1);
    return `<line class="stockPriceGridLine" x1="${left}" x2="${width - right}" y1="${py}" y2="${py}"/>` +
      `<text class="stockPriceAxis" x="${left - 10}" y="${Number(py) + 4}" text-anchor="end">${Math.round(value).toLocaleString('ko-KR')}</text>`;
  }).join('');
  const labelCount = Math.min(7, points.length);
  const axisIndices = [...new Set(Array.from({ length: labelCount }, (_, i) =>
    Math.round(i * (points.length - 1) / (labelCount - 1))))];
  const dates = axisIndices.map(i => `<text class="stockPriceAxis" x="${x(times[i]).toFixed(1)}" y="${height - 10}" text-anchor="middle">${shortDate(points[i].date)}</text>`).join('');
  const low = Math.min(...points.map(point => point.sale));
  const high = Math.max(...points.map(point => point.sale));
  const guide = (value, kind, label) => {
    const py = y(value).toFixed(1);
    return `<line class="stockPriceGuide ${kind}" x1="${left}" x2="${width - right}" y1="${py}" y2="${py}"/>` +
      `<text class="stockPriceGuideLabel ${kind}" x="${left + 5}" y="${Math.max(top + 11, Number(py) - 6)}">${label} ${won(value)}</text>`;
  };
  const guides = high === low ? guide(low, 'low', '관측가') :
    guide(high, 'high', '관측 최고가') + guide(low, 'low', '관측 최저가');
  const markers = points.map((point, i) =>
    `<circle class="stockPricePoint" cx="${x(times[i]).toFixed(1)}" cy="${y(point.sale).toFixed(1)}" r="3">` +
      `<title>${point.date} 판매가 ${won(point.sale)}${point.list == null ? '' : ` · 정가 ${won(point.list)}`}</title></circle>`).join('');
  const regular = points.some(point => point.list != null);
  host.innerHTML = `<div class="stockPriceChart"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="관측일별 정가와 판매가 추이">` +
    grid + dates + guides +
    (regular ? `<path class="stockPriceLine regular" d="${line('list')}"/>` : '') +
    `<path class="stockPriceLine sale" d="${line('sale')}"/>${markers}</svg>` +
    `<div class="stockPriceLegend">${regular ? '<span><i class="regular"></i>정가</span>' : ''}` +
    '<span><i class="sale"></i>판매가</span></div></div>';
}
