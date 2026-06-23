import { motion } from 'framer-motion';
import { Minus, Plus } from 'lucide-react';

/**
 * A single editable "engineering card" input — the building block of
 * the Dimension Workspace. Not a <form> field: a property-panel style
 * control with stepper buttons, unit suffix, and live value emphasis.
 */
export function DimensionCard({ fieldKey, label, unit, min, max, step, value, onChange }) {
  const clamp = (v) => Math.min(max ?? Infinity, Math.max(min ?? -Infinity, v));

  const handleNudge = (dir) => {
    const next = clamp(Number((value + dir * step).toFixed(4)));
    onChange(fieldKey, next);
  };

  const handleInput = (e) => {
    const raw = e.target.value;
    if (raw === '') return onChange(fieldKey, '');
    const num = Number(raw);
    if (!Number.isNaN(num)) onChange(fieldKey, num);
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="dim-card px-4 py-3 flex flex-col gap-2"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-blueprint-muted uppercase tracking-wide">
          {label}
        </span>
        <span className="text-[10px] font-mono text-blueprint-gold/70">{fieldKey}</span>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => handleNudge(-1)}
          className="h-7 w-7 flex items-center justify-center rounded-md border border-blueprint-line text-blueprint-muted hover:border-blueprint-gold hover:text-blueprint-gold transition-colors"
          aria-label={`Decrease ${label}`}
        >
          <Minus size={13} />
        </button>

        <input
          type="number"
          value={value}
          onChange={handleInput}
          min={min}
          max={max}
          step={step}
          className="flex-1 min-w-0 bg-transparent text-2xl font-display font-semibold text-blueprint-text text-center outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />

        <button
          type="button"
          onClick={() => handleNudge(1)}
          className="h-7 w-7 flex items-center justify-center rounded-md border border-blueprint-line text-blueprint-muted hover:border-blueprint-gold hover:text-blueprint-gold transition-colors"
          aria-label={`Increase ${label}`}
        >
          <Plus size={13} />
        </button>
      </div>

      <span className="text-[11px] text-blueprint-muted text-center">{unit}</span>
    </motion.div>
  );
}
