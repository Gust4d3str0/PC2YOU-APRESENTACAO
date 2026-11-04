import { formatCurrency } from '../api';

const W = 520;
const H = 190;
const PAD = { top: 18, right: 24, bottom: 42, left: 76 };
const innerW = W - PAD.left - PAD.right;
const innerH = H - PAD.top - PAD.bottom;

function xScale(i, total) {
  return PAD.left + (i / Math.max(total - 1, 1)) * innerW;
}

function yScale(value, min, range) {
  return PAD.top + innerH - ((value - min) / (range || 1)) * innerH;
}

function toLine(values, min, range, total) {
  return values
    .map((p, i) => `${xScale(i, total)},${yScale(p, min, range)}`)
    .join(' ');
}

function formatDateLabel(value) {
  const [datePart, timePart = ''] = String(value || '').split('T');
  const [, month, day] = datePart.split('-');
  const time = timePart.slice(0, 5);
  return `${day || ''}/${month || ''}${time ? ` ${time}` : ''}`;
}

export default function PriceChart({ history }) {
  if (!history || history.length < 2) {
    return (
      <p className="details-note">Histórico de preços insuficiente para exibir gráfico.</p>
    );
  }

  const minPrices = history.map((h) => Number(h.min_price));
  const avgPrices = history.map((h) => Number(h.average_price));
  const maxPrices = history.map((h) => Number(h.max_price));
  const allValues = [...minPrices, ...avgPrices, ...maxPrices].filter(Number.isFinite);

  if (!allValues.length) {
    return (
      <p className="details-note">Histórico de preços insuficiente para exibir gráfico.</p>
    );
  }

  const dataMin = Math.min(...allValues);
  const dataMax = Math.max(...allValues);
  const range = dataMax - dataMin || 1;
  const paddedMin = dataMin - range * 0.1;
  const paddedRange = (dataMax - paddedMin) * 1.1;
  const total = history.length;

  const minLine = toLine(minPrices, paddedMin, paddedRange, total);
  const avgLine = toLine(avgPrices, paddedMin, paddedRange, total);
  const maxLine = toLine(maxPrices, paddedMin, paddedRange, total);
  const gridPrices = [0, 0.33, 0.66, 1].map((t) => paddedMin + paddedRange * t);

  return (
    <div className="price-chart-wrap">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="price-chart-svg"
        aria-label="Histórico de preços"
      >
        {gridPrices.map((price, i) => {
          const y = yScale(price, paddedMin, paddedRange);
          return (
            <g key={i}>
              <line
                x1={PAD.left}
                y1={y}
                x2={W - PAD.right}
                y2={y}
                stroke="var(--border)"
                strokeWidth="1"
              />
              <text
                x={PAD.left - 6}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                fontSize="10"
                fill="var(--text-muted)"
              >
                {Number(price).toLocaleString('pt-BR', {
                  style: 'currency',
                  currency: 'BRL',
                  maximumFractionDigits: 0,
                })}
              </text>
            </g>
          );
        })}

        {history.map((h, i) => (
          <text
            key={h.date || i}
            x={xScale(i, total)}
            y={H - PAD.bottom + 22}
            textAnchor="middle"
            fontSize="10"
            fill="var(--text-muted)"
          >
            {formatDateLabel(h.date)}
          </text>
        ))}

        <polyline
          points={maxLine}
          fill="none"
          stroke="var(--orange)"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />

        <polyline
          points={avgLine}
          fill="none"
          stroke="var(--text-soft)"
          strokeWidth="1.6"
          strokeDasharray="5 3"
          strokeLinejoin="round"
        />

        <polyline
          points={minLine}
          fill="none"
          stroke="var(--primary)"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />

        {minPrices.map((p, i) => (
          <g key={`${history[i]?.date || i}-min`}>
            <circle
              cx={xScale(i, total)}
              cy={yScale(p, paddedMin, paddedRange)}
              r={4.5}
              fill="var(--primary)"
            />
            <title>
              {`${formatDateLabel(history[i]?.date)} · menor ${formatCurrency(p)} · médio ${formatCurrency(avgPrices[i])} · maior ${formatCurrency(maxPrices[i])}`}
            </title>
          </g>
        ))}
      </svg>

      <div className="price-chart-legend">
        <span className="legend-min">— Menor preço</span>
        <span className="legend-avg">- - Preço médio</span>
        <span className="legend-max">— Maior preço</span>
      </div>
    </div>
  );
}
