import { useNavigate } from 'react-router-dom';
import { ArrowRight, Loader2, AlertTriangle } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { DimensionCard } from '@/features/workspace/DimensionCard';
import { EngineeringPreview } from '@/features/workspace/EngineeringPreview';
import { DimensionLegend } from '@/features/workspace/DimensionLegend';
import { mergeTemplateFields } from '@/utils/mergeFields';
import { useWorkOrderStore } from '@/store/useWorkOrderStore';
import { generateWorkOrder } from '@/services/api';
import { COMPONENTS } from '@/data/templates';

export function WorkspacePage() {
  const navigate = useNavigate();
  const selectedTemplates = useWorkOrderStore((s) => s.selectedTemplates);
  const fieldValues = useWorkOrderStore((s) => s.fieldValues);
  const setFieldValue = useWorkOrderStore((s) => s.setFieldValue);
  const isGenerating = useWorkOrderStore((s) => s.isGenerating);
  const generationError = useWorkOrderStore((s) => s.generationError);
  const startGeneration = useWorkOrderStore((s) => s.startGeneration);
  const completeGeneration = useWorkOrderStore((s) => s.completeGeneration);
  const failGeneration = useWorkOrderStore((s) => s.failGeneration);

  const templateIds = Object.values(selectedTemplates);
  const { common, perTemplate, templates } = mergeTemplateFields(templateIds);

  const allDimensionKeys = templates.flatMap((t) => t.generatedDimensions);

  async function handleGenerate() {
    startGeneration();
    try {
      // Currently the backend accepts one template per call. We generate
      // sequentially for each selected template and merge results — this
      // keeps the UI consistent and ready for a future multi-template endpoint.
      const results = [];
      for (const tpl of templates) {
        const res = await generateWorkOrder(tpl.id, fieldValues);
        results.push({ template: tpl, ...res });
      }
      completeGeneration({
        id: `wo_${Date.now()}`,
        createdAt: new Date().toISOString(),
        results,
        inputs: fieldValues,
      });
      navigate('/result');
    } catch (err) {
      failGeneration(err.message);
    }
  }

  return (
    <div>
      <header className="mb-8">
        <h2 className="font-display text-2xl font-semibold">Engineering Workspace</h2>
        <p className="text-blueprint-muted text-sm mt-1">
          Adjust dimensions — shared fields appear once across all selected designs.
        </p>
      </header>

      <div className="grid lg:grid-cols-[1.1fr_0.9fr] gap-6">
        {/* Dimension Workspace */}
        <div className="space-y-8">
          {common.length > 0 && (
            <FieldGroup
              title="Common Dimensions"
              fields={common}
              values={fieldValues}
              onChange={setFieldValue}
            />
          )}

          {Object.entries(perTemplate).map(([templateId, { template, fields }]) => (
            <FieldGroup
              key={templateId}
              title={`${COMPONENTS[template.component]?.name} · ${template.name} Settings`}
              fields={fields}
              values={fieldValues}
              onChange={setFieldValue}
            />
          ))}

          <DimensionLegend keys={allDimensionKeys} />
        </div>

        {/* Engineering Preview */}
        <div className="space-y-4">
          <Card className="h-[420px]" withCorners>
            <EngineeringPreview fieldValues={fieldValues} templates={templates} />
          </Card>

          {generationError && (
            <div className="flex items-start gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
              <AlertTriangle size={16} className="mt-0.5" />
              <span>{generationError}</span>
            </div>
          )}

          <Button
            className="w-full justify-center text-base py-3"
            onClick={handleGenerate}
            disabled={isGenerating}
          >
            {isGenerating ? (
              <>
                <Loader2 size={16} className="animate-spin" /> Generating...
              </>
            ) : (
              <>
                Generate Work Order <ArrowRight size={16} />
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

function FieldGroup({ title, fields, values, onChange }) {
  if (!fields.length) return null;
  return (
    <section>
      <h3 className="text-xs font-mono uppercase tracking-wide text-blueprint-gold mb-3">
        {title}
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {fields.map((f) => (
          <DimensionCard
            key={f.key}
            fieldKey={f.key}
            label={f.label}
            unit={f.unit}
            min={f.min}
            max={f.max}
            step={f.step}
            value={values[f.key] ?? f.default}
            onChange={onChange}
          />
        ))}
      </div>
    </section>
  );
}
