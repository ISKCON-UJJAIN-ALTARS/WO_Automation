import BlueprintIcon from "./BlueprintIcon";

/** A single selectable card used in both the category and variant grids. */
export default function SelectCard({ icon, title, subtitle, disabledNote, onClick }) {
  return (
    <button type="button" className={`select-card ${disabledNote ? "muted" : ""}`} onClick={onClick}>
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
        <span className="select-card-flag">Live</span>
      )}
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
    </button>
  );
}
