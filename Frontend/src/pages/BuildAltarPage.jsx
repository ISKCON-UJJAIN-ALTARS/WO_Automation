import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Check, Lock, ArrowRight } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { COMPONENTS } from '@/data/templates';
import { useWorkOrderStore } from '@/store/useWorkOrderStore';

export function BuildAltarPage() {
  const navigate = useNavigate();
  const selectedComponents = useWorkOrderStore((s) => s.selectedComponents);
  const toggleComponent = useWorkOrderStore((s) => s.toggleComponent);

  const componentList = Object.values(COMPONENTS);

  return (
    <div>
      <header className="mb-8">
        <h2 className="font-display text-2xl font-semibold">Build Your Altar</h2>
        <p className="text-blueprint-muted text-sm mt-1">
          Select the components you want to include in this work order.
        </p>
      </header>

      {/* Visual altar diagram */}
      <Card className="p-8 mb-10 flex flex-col items-center gap-3" withCorners>
        <DiagramBlock
          label="Ceiling"
          active={selectedComponents.includes('ceiling')}
        />
        <div className="flex gap-4">
          <DiagramBlock label="Pillar" small active={selectedComponents.includes('pillars')} />
          <DiagramBlock label="Pillar" small active={selectedComponents.includes('pillars')} />
        </div>
        <DiagramBlock
          label="Base Box"
          wide
          active={selectedComponents.includes('base_box')}
        />
      </Card>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {componentList.map((c) => {
          const selected = selectedComponents.includes(c.id);
          const disabled = c.status === 'coming_soon';
          return (
            <motion.button
              key={c.id}
              whileHover={!disabled ? { y: -3 } : {}}
              disabled={disabled}
              onClick={() => toggleComponent(c.id)}
              className="text-left"
            >
              <Card
                className={`p-4 h-full flex flex-col gap-2 transition-all ${
                  selected ? 'border-blueprint-gold shadow-gold' : ''
                } ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm">{c.name}</span>
                  {selected ? (
                    <Check size={15} className="text-blueprint-gold" />
                  ) : disabled ? (
                    <Lock size={13} className="text-blueprint-muted" />
                  ) : null}
                </div>
                <p className="text-xs text-blueprint-muted leading-relaxed">{c.description}</p>
                {disabled && (
                  <span className="text-[10px] font-mono uppercase text-blueprint-gold/70 mt-auto">
                    Coming soon
                  </span>
                )}
              </Card>
            </motion.button>
          );
        })}
      </div>

      <div className="flex justify-end mt-10">
        <Button
          disabled={selectedComponents.length === 0}
          onClick={() => navigate('/design')}
        >
          Continue to Design <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  );
}

function DiagramBlock({ label, active, wide, small }) {
  return (
    <div
      className={`flex items-center justify-center rounded-md border text-xs font-mono transition-colors ${
        active
          ? 'border-blueprint-gold text-blueprint-gold bg-blueprint-goldSoft'
          : 'border-blueprint-line text-blueprint-muted'
      } ${wide ? 'w-64 h-12' : small ? 'w-16 h-16' : 'w-40 h-12'}`}
    >
      {label}
    </div>
  );
}
