import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, LayoutTemplate } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { COMPONENTS, getTemplatesForComponent } from '@/data/templates';
import { useWorkOrderStore } from '@/store/useWorkOrderStore';

export function ChooseDesignPage() {
  const navigate = useNavigate();
  const selectedComponents = useWorkOrderStore((s) => s.selectedComponents);
  const selectedTemplates = useWorkOrderStore((s) => s.selectedTemplates);
  const selectTemplate = useWorkOrderStore((s) => s.selectTemplate);

  const allChosen = selectedComponents.every((c) => selectedTemplates[c]);

  return (
    <div>
      <header className="mb-8">
        <h2 className="font-display text-2xl font-semibold">Choose Design</h2>
        <p className="text-blueprint-muted text-sm mt-1">
          Pick a design for each component you selected.
        </p>
      </header>

      <div className="space-y-10">
        {selectedComponents.map((componentId) => (
          <section key={componentId}>
            <h3 className="text-sm font-mono uppercase tracking-wide text-blueprint-gold mb-4">
              {COMPONENTS[componentId]?.name}
            </h3>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {getTemplatesForComponent(componentId).map((tpl) => {
                const selected = selectedTemplates[componentId] === tpl.id;
                return (
                  <motion.div key={tpl.id} whileHover={{ y: -4 }}>
                    <Card
                      className={`overflow-hidden flex flex-col h-full ${
                        selected ? 'border-blueprint-gold shadow-gold' : ''
                      }`}
                    >
                      <div className="h-36 bg-blueprint-bg flex items-center justify-center border-b border-blueprint-line">
                        <LayoutTemplate size={36} className="text-blueprint-gold/50" />
                      </div>
                      <div className="p-4 flex flex-col gap-3 flex-1">
                        <div>
                          <h4 className="font-medium text-sm">{tpl.name}</h4>
                          <p className="text-xs text-blueprint-muted mt-1 leading-relaxed">
                            {tpl.description}
                          </p>
                        </div>
                        <span className="text-[11px] font-mono text-blueprint-muted">
                          {tpl.generatedDimensions.length} dimensions generated
                        </span>
                        <Button
                          variant={selected ? 'primary' : 'subtle'}
                          className="mt-auto w-full justify-center"
                          onClick={() => selectTemplate(componentId, tpl.id)}
                        >
                          {selected ? 'Selected' : 'Select Design'}
                        </Button>
                      </div>
                    </Card>
                  </motion.div>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      <div className="flex justify-end mt-10">
        <Button disabled={!allChosen} onClick={() => navigate('/workspace')}>
          Continue to Workspace <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  );
}
