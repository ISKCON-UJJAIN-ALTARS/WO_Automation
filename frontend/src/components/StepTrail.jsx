/** Dimension-line styled progress indicator for the wizard. */
export default function StepTrail({ step, categoryLabel, variantLabel }) {
  const steps = [
    { n: 1, label: "Component(s)", value: categoryLabel },
    { n: 2, label: "Variant(s)", value: variantLabel },
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