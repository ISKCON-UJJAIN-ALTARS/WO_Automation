/** Signature input element: an arrowed dimension line instead of a boxed field. */
export default function DimensionField({ field, value, error, onChange, hint }) {
  return (
    <div className={`dim-field ${error ? "error" : ""}`}>
      <div className="dim-label-row">
        <span className="dim-label">{field.label}</span>
        {hint && <span className="dim-shared-badge">{hint}</span>}
        <span className="dim-unit">{field.unit}</span>
      </div>
      <div className="dim-line">
        <span className="dim-track" />
        <input
          className="dim-input"
          type={"number" || "char"} 
          inputMode={"decimal" || "text"} 
          step={field.integer ? "1" : "any"}
          placeholder={field.integer ? "0" : "0.0"}
          value={value}
          onChange={(e) => onChange(field.key, e.target.value)}
        />
      </div>
      <div className="dim-err-msg">{error || ""}</div>
    </div>
  );
}