import { Outlet, Link, useLocation } from 'react-router-dom';
import { Compass } from 'lucide-react';

const steps = [
  { path: '/build', label: 'Build' },
  { path: '/design', label: 'Design' },
  { path: '/workspace', label: 'Workspace' },
  { path: '/result', label: 'Result' },
];

export function AppLayout() {
  const { pathname } = useLocation();
  const showSteps = pathname !== '/';

  return (
    <div className="min-h-screen blueprint-bg">
      <header className="sticky top-0 z-30 backdrop-blur-md bg-blueprint-bg/80 border-b border-blueprint-line">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 group">
            <span className="h-8 w-8 rounded-md bg-blueprint-gold/10 border border-blueprint-gold/40 flex items-center justify-center group-hover:bg-blueprint-gold/20 transition-colors">
              <Compass size={16} className="text-blueprint-gold" />
            </span>
            <span className="font-display font-semibold tracking-tight text-sm sm:text-base">
              Divine Sky <span className="text-blueprint-gold">Work Order Studio</span>
            </span>
          </Link>

          {showSteps && (
            <nav className="hidden md:flex items-center gap-1 text-xs font-mono text-blueprint-muted">
              {steps.map((s, i) => (
                <span key={s.path} className="flex items-center gap-1">
                  <span
                    className={pathname.startsWith(s.path) ? 'text-blueprint-gold' : ''}
                  >
                    0{i + 1} {s.label}
                  </span>
                  {i < steps.length - 1 && <span className="mx-1 opacity-40">/</span>}
                </span>
              ))}
            </nav>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-10">
        <Outlet />
      </main>
    </div>
  );
}
