/**
 * Tiny SVG line-drawing icons echoing the real engineering drawings in
 * backend/templates/*.png — used on category and variant selection cards
 * instead of generic stock icons.
 */
export default function BlueprintIcon({ kind, size = 56 }) {
  const stroke = "var(--ink)";
  const accent = "var(--red)";
  const common = {
    fill: "none",
    stroke,
    strokeWidth: 1.6,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  };

  let content;
  switch (kind) {
    case "ceiling":
      content = (
        <>
          <path d="M6 30 L6 16 L16 16 L16 10 L34 10 L34 16 L44 16 L44 30" {...common} />
          <line x1="2" y1="34" x2="48" y2="34" stroke={accent} strokeWidth="1.2" strokeDasharray="2 2" />
        </>
      );
      break;
    case "basebox":
      content = (
        <>
          <rect x="8" y="12" width="34" height="26" {...common} />
          <line x1="8" y1="20" x2="42" y2="20" stroke={accent} strokeWidth="1.2" />
          <line x1="20" y1="20" x2="20" y2="38" stroke={accent} strokeWidth="1.2" />
        </>
      );
      break;
    case "dome3":
      content = (
        <>
          <path
            d="M6 14 L6 8 L14 8 L14 14 L20 14 L20 9 L28 9 L28 14 L34 14 L34 8 L42 8 L42 14"
            {...common}
          />
          <line x1="6" y1="14" x2="42" y2="14" {...common} />
          <line x1="6" y1="14" x2="6" y2="26" {...common} />
          <line x1="42" y1="14" x2="42" y2="26" {...common} />
          <line x1="6" y1="26" x2="42" y2="26" {...common} />
          <line x1="14" y1="11" x2="34" y2="11" stroke={accent} strokeWidth="1" strokeDasharray="1.5 1.5" />
        </>
      );
      break;
    case "dome4":
      content = (
        <>
          <path
            d="M4 16 L4 9 L11 9 L11 16 L17 16 L17 10 L23 10 L23 16 L29 16 L29 10 L35 10 L35 16 L41 16 L41 9 L48 9 L48 16"
            {...common}
          />
          <line x1="4" y1="16" x2="48" y2="16" {...common} />
          <line x1="4" y1="16" x2="4" y2="27" {...common} />
          <line x1="48" y1="16" x2="48" y2="27" {...common} />
          <line x1="4" y1="27" x2="48" y2="27" {...common} />
          <line x1="11" y1="12" x2="41" y2="12" stroke={accent} strokeWidth="1" strokeDasharray="1.5 1.5" />
        </>
      );
      break;
    case "box":
      content = (
        <>
          <rect x="8" y="10" width="34" height="24" {...common} />
          <rect x="14" y="16" width="9" height="12" stroke={accent} strokeWidth="1.2" fill="none" />
          <rect x="27" y="16" width="9" height="12" stroke={accent} strokeWidth="1.2" fill="none" />
        </>
      );
      break;
    default:
      content = <rect x="8" y="8" width="32" height="32" {...common} />;
  }

  return (
    <svg width={size} height={size} viewBox="0 0 50 42" aria-hidden="true">
      {content}
    </svg>
  );
}
