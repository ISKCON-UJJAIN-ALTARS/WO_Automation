import { useNavigate } from 'react-router-dom';
import { Download, Maximize2, RotateCcw, FileText } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { useWorkOrderStore } from '@/store/useWorkOrderStore';
import { resolveImageUrl } from '@/services/api';
import { DIMENSION_LEGEND } from '@/data/templates';

export function ResultPage() {
  const navigate = useNavigate();
  const currentOrder = useWorkOrderStore((s) => s.currentOrder);
  const resetFlow = useWorkOrderStore((s) => s.resetFlow);

  if (!currentOrder) {
    return (
      <div className="text-center py-20">
        <p className="text-blueprint-muted mb-4">No work order has been generated yet.</p>
        <Button onClick={() => navigate('/build')}>Start a Work Order</Button>
      </div>
    );
  }

  return (
    <div>
      <header className="mb-8">
        <h2 className="font-display text-2xl font-semibold">Generated Work Order</h2>
        <p className="text-blueprint-muted text-sm mt-1">
          {new Date(currentOrder.createdAt).toLocaleString()}
        </p>
      </header>

      <div className="space-y-10">
        {currentOrder.results.map((r, idx) => (
          <div key={idx} className="grid lg:grid-cols-[1.3fr_0.7fr] gap-6">
            <Card className="overflow-hidden" withCorners>
              <div className="border-b border-blueprint-line px-4 py-3 flex items-center justify-between">
                <span className="text-sm font-medium">{r.template.name}</span>
                <span className="text-[11px] font-mono text-blueprint-muted">
                  DWG-{String(idx + 1).padStart(2, '0')}
                </span>
              </div>
              <div className="aspect-[4/3] flex items-center justify-center bg-blueprint-bg">
                {r.image_path ? (
                  <img
                    src={resolveImageUrl(r.image_path)}
                    alt={`${r.template.name} drawing`}
                    className="max-h-full max-w-full object-contain"
                  />
                ) : (
                  <FileText size={40} className="text-blueprint-muted" />
                )}
              </div>
            </Card>

            <Card className="p-5">
              <h4 className="text-xs font-mono uppercase tracking-wide text-blueprint-gold mb-4">
                Generated Dimensions
              </h4>
              <div className="space-y-2">
                {Object.entries(r.values || {}).map(([k, v]) => (
                  <div
                    key={k}
                    className="flex items-center justify-between text-sm border-b border-blueprint-line/60 pb-2"
                  >
                    <span className="font-mono text-blueprint-muted">
                      {k} <span className="opacity-60">({DIMENSION_LEGEND[k] || k})</span>
                    </span>
                    <span className="font-medium">{v}</span>
                  </div>
                ))}
              </div>

              <div className="flex flex-col gap-2 mt-6">
                <Button
                  variant="subtle"
                  className="justify-center"
                  onClick={() => window.open(resolveImageUrl(r.image_path), '_blank')}
                >
                  <Download size={15} /> Download PNG
                </Button>
                <Button
                  variant="subtle"
                  className="justify-center"
                  onClick={() => window.open(resolveImageUrl(r.image_path), '_blank')}
                >
                  <Maximize2 size={15} /> Open Full Screen
                </Button>
                <Button variant="ghost" disabled className="justify-center">
                  <FileText size={15} /> Download PDF (Coming Soon)
                </Button>
              </div>
            </Card>
          </div>
        ))}
      </div>

      <div className="flex justify-center mt-10">
        <Button
          variant="ghost"
          onClick={() => {
            resetFlow();
            navigate('/build');
          }}
        >
          <RotateCcw size={15} /> Generate Another
        </Button>
      </div>
    </div>
  );
}
