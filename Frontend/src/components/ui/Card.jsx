import { cn } from '@/utils/cn';

export function Card({ className, children, withCorners = false, ...props }) {
  return (
    <div
      className={cn(
        'relative rounded-xl bg-blueprint-card border border-blueprint-line',
        className
      )}
      {...props}
    >
      {withCorners && (
        <>
          <span className="crosshair-corner -top-px -left-px border-r-0 border-b-0 rounded-tl-md" />
          <span className="crosshair-corner -top-px -right-px border-l-0 border-b-0 rounded-tr-md" />
          <span className="crosshair-corner -bottom-px -left-px border-r-0 border-t-0 rounded-bl-md" />
          <span className="crosshair-corner -bottom-px -right-px border-l-0 border-t-0 rounded-br-md" />
        </>
      )}
      {children}
    </div>
  );
}
