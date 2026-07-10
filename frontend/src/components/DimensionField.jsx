/** Signature input element: an arrowed dimension line instead of a boxed field. */
export default function DimensionField({ field, value, error, onChange, hint }) {
  const type = field.type || "number";

  return (
    <div className={`dim-field ${error ? "error" : ""}`}>
      <div className="dim-label-row">
        <span className="dim-label">{field.label}</span>
        {hint && <span className="dim-shared-badge">{hint}</span>}
        {field.unit && <span className="dim-unit">{field.unit}</span>}
      </div>
      <div className="dim-line">
        <span className="dim-track" />
        {type === "select" ? (
          <select
            className="dim-input dim-select"
            value={value ?? ""}
            onChange={(e) => onChange(field.key, e.target.value)}
          >
            <option value="" disabled>
              Select...
            </option>
            {(field.options || []).map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            className="dim-input"
            type={type === "number" ? "number" : "text"}
            inputMode={type === "number" ? "decimal" : "text"}
            step={type === "number" ? (field.integer ? "1" : "any") : undefined}
            placeholder={type === "number" ? (field.integer ? "0" : "0.0") : ""}
            value={value ?? ""}
            onChange={(e) => onChange(field.key, e.target.value)}
          />
        )}
      </div>
      <div className="dim-err-msg">{error || ""}</div>
    </div>
  );
}