import { useMemo } from 'react';

/**
 * Renders a stylized engineering-drawing preview that reshapes itself
 * based on current field values. This does NOT call the backend —
 * it's a visual confidence check before generation, per spec.
 */
export function EngineeringPreview({ fieldValues, templates }) {
  const length = Number(fieldValues.altar_length) || 72;
  const depth = Number(fieldValues.altar_depth) || 22;
  const pillarW = Number(fieldValues.pillar_width) || 3.5;
  const pillarH = Number(fieldValues.pillar_height) || 25;
  const domeCount = Number(fieldValues.dome_count) || 3;

  const hasCeiling = templates.some((t) => t.component === 'ceiling');
  const hasBase = templates.some((t) => t.component === 'base_box');

  const scale = useMemo(() => Math.min(1, 280 / Math.max(length, 1)), [length]);
  const w = length * scale;
  const pw = pillarW * scale * 4;
  const ph = pillarH * scale;

  const domes = Array.from({ length: Math.min(domeCount, 5) });

  return (
    <div className="relative w-full h-full flex items-center justify-center overflow-hidden">
      <svg viewBox="0 0 360 260" className="w-full h-full max-w-md" fill="none">
        <rect
          x="2"
          y="2"
          width="356"
          height="256"
          stroke="#2A3B57"
          strokeWidth="1"
          fill="none"
        />
        <g transform={`translate(${180 - w / 2}, 70)`}>
          {hasCeiling && (
            <g>
              {domes.map((_, i) => {
                const domeW = w / domes.length;
                const cx = domeW * i + domeW / 2;
                return (
                  <path
                    key={i}
                    d={`M ${cx - domeW / 2 + 4} 20 Q ${cx} -${10 + ph * 0.15} ${
                      cx + domeW / 2 - 4
                    } 20`}
                    stroke="#D4AF37"
                    strokeWidth="1.5"
                    className="animate-draw"
                    style={{ strokeDasharray: 200 }}
                  />
                );
              })}
              <line x1="0" y1="20" x2={w} y2="20" stroke="#D4AF37" strokeWidth="1.5" />
            </g>
          )}

          <line x1={4} y1="20" x2={4} y2={20 + ph} stroke="#F8FAFC" strokeWidth={Math.max(pw, 3)} opacity="0.85" />
          <line
            x1={w - 4}
            y1="20"
            x2={w - 4}
            y2={20 + ph}
            stroke="#F8FAFC"
            strokeWidth={Math.max(pw, 3)}
            opacity="0.85"
          />

          {hasBase && (
            <rect
              x="0"
              y={20 + ph}
              width={w}
              height={depth * scale * 0.9}
              stroke="#94A3B8"
              strokeWidth="1.2"
              fill="rgba(148,163,184,0.05)"
            />
          )}

          {/* dimension lines */}
          <g stroke="#D4AF37" strokeWidth="0.75" opacity="0.6">
            <line x1="0" y1={20 + ph + (depth * scale * 0.9) + 16} x2={w} y2={20 + ph + (depth * scale * 0.9) + 16} />
            <line x1="0" y1={20 + ph + (depth * scale * 0.9) + 10} x2="0" y2={20 + ph + (depth * scale * 0.9) + 22} />
            <line x1={w} y1={20 + ph + (depth * scale * 0.9) + 10} x2={w} y2={20 + ph + (depth * scale * 0.9) + 22} />
          </g>
          <text
            x={w / 2}
            y={20 + ph + (depth * scale * 0.9) + 30}
            fill="#94A3B8"
            fontSize="9"
            textAnchor="middle"
            fontFamily="monospace"
          >
            {length}" OAL
          </text>
        </g>
      </svg>

      <div className="absolute top-3 left-3 text-[10px] font-mono text-blueprint-muted">
        SCALE NTS &middot; LIVE PREVIEW
      </div>
    </div>
  );
}
