import { useState } from "react";

import { CATEGORIES, VARIANTS, findCategory, findVariant } from "./templateConfig";
import { generateDrawing } from "./api";
import useApiHealth from "./hooks/useApiHealth";

import StepTrail from "./components/StepTrail";
import SelectCard from "./components/SelectCard";
import BlueprintIcon from "./components/BlueprintIcon";
import DimensionField from "./components/DimensionField";
import ResultView from "./components/ResultView";

const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function App() {
  const [step, setStep] = useState(1); // 1 = category, 2 = variant, 3 = form/result
  const [categoryKey, setCategoryKey] = useState(null);
  const [variantKey, setVariantKey] = useState(null);

  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});

  const [submitting, setSubmitting] = useState(false);
  const [banner, setBanner] = useState(null); // { kind: 'error' | 'info', title, message }
  const [result, setResult] = useState(null); // { image_path, values }

  const { apiBase, setApiBase, status: apiStatus, checkApi } = useApiHealth(DEFAULT_API_BASE);

  const category = findCategory(categoryKey);
  const variant = findVariant(categoryKey, variantKey);

  function chooseCategory(key) {
    setCategoryKey(key);
    setVariantKey(null);
    setValues({});
    setErrors({});
    setBanner(null);
    setResult(null);
    setStep(2);
  }

  function chooseVariant(v) {
    setVariantKey(v.key);
    setValues({});
    setErrors({});
    setBanner(null);
    setResult(null);
    setStep(3);
  }

  function goBackTo(targetStep) {
    setBanner(null);
    if (targetStep <= 1) {
      setCategoryKey(null);
      setVariantKey(null);
    } else if (targetStep <= 2) {
      setVariantKey(null);
      setResult(null);
    }
    setStep(targetStep);
  }

  function handleFieldChange(key, raw) {
    setValues((prev) => ({ ...prev, [key]: raw }));
    setErrors((prev) => ({ ...prev, [key]: null }));
  }

  function validate() {
    if (!variant) return null;
    const nextErrors = {};
    const inputs = {};
    let ok = true;

    variant.fields.forEach((f) => {
      const raw = (values[f.key] ?? "").toString().trim();
      if (raw === "") {
        nextErrors[f.key] = "Required";
        ok = false;
        return;
      }
      const num = Number(raw);
      if (Number.isNaN(num)) {
        nextErrors[f.key] = "Must be a number";
        ok = false;
        return;
      }
      if (f.integer && !Number.isInteger(num)) {
        nextErrors[f.key] = "Must be a whole number";
        ok = false;
        return;
      }
      if (num <= 0) {
        nextErrors[f.key] = "Must be greater than 0";
        ok = false;
        return;
      }
      inputs[f.key] = num;
    });

    setErrors(nextErrors);
    return ok ? inputs : null;
  }

  async function handleSubmit() {
    setBanner(null);

    if (!variant.wired) {
      setBanner({
        kind: "info",
        title: "Not wired up yet",
        message: `"${variant.key}" has a request schema on the backend but no entry in template_mappings.json and no matching Excel sheet. Submitting will return a 404 from /generate until that config is added — this form will work the moment it is.`,
      });
      return;
    }

    const inputs = validate();
    if (!inputs) return;

    setSubmitting(true);
    try {
      const data = await generateDrawing(apiBase, variant.key, inputs);
      setResult(data);
    } catch (err) {
      if (err.status) {
        setBanner({
          kind: "error",
          title: `Backend rejected the request (${err.status})`,
          message: err.message,
        });
      } else {
        setBanner({
          kind: "error",
          title: "Could not reach backend",
          message: `${err.message}. Check that the API base points to a running server and that CORS is enabled there.`,
        });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="wrap">
      <header className="top">
        <div className="brand">
          <span className="brand-mark">
            Divine Sky <em>Work Order</em>
          </span>
        </div>
        <div className="doc-no">
          CUTTING SPEC GENERATOR
          <br />
          <span className="val">{new Date().toISOString().slice(0, 16).replace("T", " ")}</span>
        </div>
      </header>

      <div className="api-base-row">
        <span
          className={`api-dot ${apiStatus.state === "ok" ? "ok" : apiStatus.state === "bad" ? "bad" : ""}`}
        />
        <span>API&nbsp;BASE</span>
        <input
          value={apiBase}
          spellCheck={false}
          onChange={(e) => setApiBase(e.target.value)}
          onBlur={(e) => checkApi(e.target.value.trim().replace(/\/$/, ""))}
        />
        <span className="api-status-text">{apiStatus.text}</span>
      </div>

      <StepTrail step={step} categoryLabel={category?.label} variantLabel={variant?.label} />

      {step === 1 && (
        <section className="panel">
          <div className="panel-head">
            <h2>What are you cutting?</h2>
            <span className="tag">Step 1 of 3</span>
          </div>
          <div className="panel-body">
            <div className="card-grid">
              {CATEGORIES.map((c) => (
                <SelectCard
                  key={c.key}
                  icon={c.icon}
                  title={c.label}
                  subtitle={c.blurb}
                  onClick={() => chooseCategory(c.key)}
                />
              ))}
            </div>
          </div>
        </section>
      )}

      {step === 2 && category && (
        <section className="panel">
          <div className="panel-head">
            <h2>Choose a {category.label} variant</h2>
            <span className="tag">Step 2 of 3</span>
          </div>
          <div className="panel-body">
            <button className="back-link" onClick={() => goBackTo(1)}>
              ← Back to component type
            </button>
            <div className="card-grid">
              {(VARIANTS[category.key] || []).map((v) => (
                <SelectCard
                  key={v.key}
                  icon={v.icon}
                  title={v.label}
                  subtitle={v.sub}
                  disabledNote={v.wired ? null : "No config yet"}
                  onClick={() => chooseVariant(v)}
                />
              ))}
            </div>
          </div>
        </section>
      )}

      {step === 3 && variant && (
        <div className="grid-2col">
          <section className="panel">
            <div className="panel-head">
              <h2>Altar Dimensions</h2>
              <span className="tag">{variant.wired ? "Input · Sheet" : "No sheet mapped"}</span>
            </div>
            <div className="panel-body">
              <button className="back-link" onClick={() => goBackTo(2)}>
                ← Back to variant
              </button>

              <div className="variant-summary">
                <BlueprintIcon kind={variant.icon} size={40} />
                <div>
                  <div className="variant-summary-title">
                    {category.label} · {variant.label}
                  </div>
                  <div className="variant-summary-sub">{variant.sub}</div>
                </div>
              </div>

              {banner && (
                <div className={`banner ${banner.kind === "info" ? "info" : ""}`}>
                  <strong>{banner.title}</strong>
                  {banner.message}
                </div>
              )}

              <form onSubmit={(e) => e.preventDefault()}>
                {variant.fields.map((f) => (
                  <DimensionField
                    key={f.key}
                    field={f}
                    value={values[f.key] ?? ""}
                    error={errors[f.key]}
                    onChange={handleFieldChange}
                  />
                ))}
              </form>

              <div className="submit-row">
                <button className="submit-btn" disabled={submitting} onClick={handleSubmit}>
                  {submitting ? (
                    <>
                      <span className="spinner" /> Generating…
                    </>
                  ) : (
                    "Generate Drawing"
                  )}
                </button>
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Generated Drawing</h2>
              <span className="tag">{result ? "Generated" : submitting ? "Processing…" : "Awaiting input"}</span>
            </div>
            <div className="panel-body">
              {!result && (
                <div className="result-empty">
                  <svg width="64" height="64" viewBox="0 0 64 64" fill="none" aria-hidden="true">
                    <rect x="8" y="8" width="48" height="48" stroke="#8A8A80" strokeWidth="1.5" strokeDasharray="4 4" />
                    <path d="M20 32h24M32 20v24" stroke="#8A8A80" strokeWidth="1.5" />
                  </svg>
                  <p>
                    Fill in the dimensions and generate to see the rendered cutting drawing, with every
                    calculated value listed below it.
                  </p>
                </div>
              )}
              {result && <ResultView apiBase={apiBase} data={result} />}
            </div>
          </section>
        </div>
      )}

      <footer>
        <span>Excel remains the source of truth — Python performs zero calculations.</span>
        <span>{variant ? `template: ${variant.key}` : "no template selected"}</span>
      </footer>
    </div>
  );
}
