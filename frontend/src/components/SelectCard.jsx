import BlueprintIcon from "./BlueprintIcon";

/**
 * A single selectable card used in the category, variant, and multi-select
 * grids.
 *
 * - Default (single-select) mode: click navigates forward, shows an arrow.
 * - `multi` mode: click toggles `selected`, shows a checkbox instead of an
 *   arrow, and the card stays on screen so more than one can be picked.
 */
export default function SelectCard({ icon, title, subtitle, disabledNote, selected, multi, onClick }) {
  return (
    <button
      type="button"
      className={`select-card ${disabledNote ? "muted" : ""} ${selected ? "selected" : ""}`}
      aria-pressed={multi ? !!selected : undefined}
      onClick={onClick}
    >
      <div className="select-card-icon">
        <BlueprintIcon kind={icon} />
      </div>
      <div className="select-card-text">
        <span className="select-card-title">{title}</span>
        <span className="select-card-sub">{subtitle}</span>
      </div>
      {disabledNote ? (
        <span className="select-card-flag muted-flag">{disabledNote}</span>
      ) : (
        !multi && <span className="select-card-flag">Live</span>
      )}
      {multi ? (
        <span className={`select-card-check ${selected ? "checked" : ""}`} aria-hidden="true">
          {selected && (
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
              <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </span>
      ) : (
        <svg className="select-card-arrow" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path
            d="M3 8h10M9 4l4 4-4 4"
            stroke="currentColor"
            strokeWidth="1.5"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  );
}