import { cn } from '@/utils/cn';

const variants = {
  primary:
    'bg-blueprint-gold text-blueprint-bg hover:brightness-110 shadow-gold font-semibold',
  ghost:
    'bg-transparent border border-blueprint-line text-blueprint-text hover:border-blueprint-gold hover:text-blueprint-gold',
  subtle:
    'bg-blueprint-card border border-blueprint-line text-blueprint-text hover:border-blueprint-gold/60',
};

export function Button({ variant = 'primary', className, children, ...props }) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-lg px-5 py-2.5 text-sm transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed',
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
