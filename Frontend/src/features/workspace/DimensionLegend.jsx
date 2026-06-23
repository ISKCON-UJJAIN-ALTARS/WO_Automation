import { useState } from 'react';
import { ChevronDown, BookOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card } from '@/components/ui/Card';
import { DIMENSION_LEGEND } from '@/data/templates';

export function DimensionLegend({ keys }) {
  const [open, setOpen] = useState(false);
  const entries = keys.length
    ? keys.map((k) => [k, DIMENSION_LEGEND[k] || 'Unknown'])
    : Object.entries(DIMENSION_LEGEND);

  return (
    <Card className="overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-blueprint-text"
      >
        <span className="flex items-center gap-2">
          <BookOpen size={15} className="text-blueprint-gold" />
          Engineering Legend
        </span>
        <ChevronDown
          size={16}
          className={`text-blueprint-muted transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="px-4 pb-4"
          >
            <div className="grid grid-cols-2 gap-2 text-xs">
              {entries.map(([abbr, full]) => (
                <div key={abbr} className="flex items-baseline gap-1.5">
                  <span className="font-mono text-blueprint-gold">{abbr}</span>
                  <span className="text-blueprint-muted">→ {full}</span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  );
}
