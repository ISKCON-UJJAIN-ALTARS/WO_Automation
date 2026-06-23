import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Ruler } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useWorkOrderStore } from '@/store/useWorkOrderStore';

export function WelcomePage() {
  const navigate = useNavigate();
  const resetFlow = useWorkOrderStore((s) => s.resetFlow);

  return (
    <div className="relative min-h-[78vh] flex items-center justify-center text-center overflow-hidden">
      <svg
        className="absolute inset-0 w-full h-full opacity-30 pointer-events-none"
        viewBox="0 0 800 600"
      >
        <g stroke="#D4AF37" strokeWidth="0.6" opacity="0.5">
          <path d="M150 420 Q 400 220 650 420" className="animate-draw" style={{ strokeDasharray: 900 }} />
          <line x1="150" y1="420" x2="150" y2="500" />
          <line x1="650" y1="420" x2="650" y2="500" />
          <line x1="150" y1="520" x2="650" y2="520" />
        </g>
      </svg>

      <div className="relative z-10 max-w-2xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-blueprint-gold/40 bg-blueprint-goldSoft text-blueprint-gold text-xs font-mono mb-6"
        >
          <Ruler size={12} /> Manufacturing Drawing Generator
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="font-display text-4xl sm:text-5xl font-semibold tracking-tight"
        >
          Divine Sky <span className="text-blueprint-gold">Work Order Studio</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="mt-4 text-blueprint-muted text-base sm:text-lg"
        >
          Generate technical altar manufacturing drawings in minutes.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.18 }}
          className="mt-9"
        >
          <Button
            onClick={() => {
              resetFlow();
              navigate('/build');
            }}
            className="text-base px-7 py-3"
          >
            Create New Work Order <ArrowRight size={16} />
          </Button>
        </motion.div>
      </div>
    </div>
  );
}
