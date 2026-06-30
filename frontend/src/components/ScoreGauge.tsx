interface ScoreGaugeProps {
  score: number;
  size?: number;
  strokeWidth?: number;
}

function severityColor(score: number): string {
  if (score <= 30) return '#466cf3';
  if (score <= 55) return '#e6e51e';
  if (score <= 75) return '#ff8562';
  return '#f34646';
}

function severityLabel(score: number): string {
  if (score <= 30) return 'In Control';
  if (score <= 55) return 'Moderate';
  if (score <= 75) return 'High';
  return 'Critical';
}

export function ScoreGauge({ score, size = 220, strokeWidth = 18 }: ScoreGaugeProps) {
  const clampedScore = Math.max(0, Math.min(100, score));
  const radius = (size - strokeWidth) / 2;
  const center = size / 2;

  // Arc from 210° to 330° (270° sweep) — bottom-open horseshoe
  const startAngle = 210;
  const totalSweep = 300;

  function polar(angleDeg: number, r: number) {
    const rad = ((angleDeg - 90) * Math.PI) / 180;
    return {
      x: center + r * Math.cos(rad),
      y: center + r * Math.sin(rad),
    };
  }

  function arcPath(from: number, to: number, r: number, large: boolean) {
    const s = polar(from, r);
    const e = polar(to, r);
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large ? 1 : 0} 1 ${e.x} ${e.y}`;
  }

  const trackPath = arcPath(startAngle, startAngle + totalSweep, radius, true);

  const fillSweep = (clampedScore / 100) * totalSweep;
  const fillLarge = fillSweep > 180;
  const fillPath = fillSweep > 0
    ? arcPath(startAngle, startAngle + fillSweep, radius, fillLarge)
    : null;

  const color = severityColor(clampedScore);
  const label = severityLabel(clampedScore);

  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
      <div className="score-ring-wrap" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} fill="none">
          <path
            d={trackPath}
            stroke="#e6e6e6"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            fill="none"
          />
          {fillPath && (
            <path
              d={fillPath}
              stroke={color}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              fill="none"
              style={{ transition: 'stroke-dashoffset 0.6s ease' }}
            />
          )}
        </svg>
        <div className="score-center-text">
          <div
            style={{
              fontFamily: 'var(--font-poppins)',
              fontWeight: 700,
              fontSize: 52,
              lineHeight: 1,
              letterSpacing: '-3px',
              color: 'var(--color-carbon)',
            }}
          >
            {clampedScore}
          </div>
          <div
            style={{
              fontFamily: 'var(--font-inter)',
              fontSize: 13,
              color: 'var(--color-carbon)',
              opacity: 0.45,
              marginTop: 6,
              letterSpacing: '0.5px',
              textTransform: 'uppercase',
            }}
          >
            / 100
          </div>
        </div>
      </div>
      <span
        className="tag"
        style={{
          background: color,
          borderColor: color,
          color: clampedScore <= 55 && clampedScore > 30 ? '#000' : clampedScore <= 30 ? '#fff' : '#fff',
          fontFamily: 'var(--font-inter)',
          fontWeight: 500,
          fontSize: 15,
          padding: '7px 20px',
        }}
      >
        {label}
      </span>
    </div>
  );
}
