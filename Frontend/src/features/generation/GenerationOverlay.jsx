import { motion } from 'framer-motion';
import { Compass } from 'lucide-react';

export function GenerationOverlay() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 blueprint-bg flex items-center justify-center"
    >
      <div className="text-center">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 2.4, ease: 'linear' }}
          className="mx-auto mb-6 h-16 w-16 rounded-full border-2 border-dashed border-blueprint-gold/50 flex items-center justify-center"
        >
          <Compass size={26} className="text-blueprint-gold" />
        </motion.div>
        <p className="font-display text-lg">Drafting your manufacturing drawing…</p>
        <p className="text-blueprint-muted text-sm mt-1">Calculating dimensions on the workshop floor</p>
      </div>
    </motion.div>
  );
}
