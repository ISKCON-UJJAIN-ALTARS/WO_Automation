/** Dimension-line styled progress indicator for the 3-step wizard. */
export default function StepTrail({ step, categoryLabel, variantLabel }) {
  const steps = [
    { n: 1, label: "Component", value: categoryLabel },
    { n: 2, label: "Variant", value: variantLabel },
    { n: 3, label: "Dimensions", value: null },
  ];

  return (
    <div className="step-trail">
      {steps.map((s, i) => (
        <div key={s.n} className={`step-node ${step === s.n ? "active" : ""} ${step > s.n ? "done" : ""}`}>
          <div className="step-dot">{step > s.n ? "✓" : s.n}</div>
          <div className="step-text">
            <span className="step-label">{s.label}</span>
            {s.value && <span className="step-value">{s.value}</span>}
          </div>
          {i < steps.length - 1 && <div className="step-line" />}
        </div>
      ))}
    </div>
  );
}
