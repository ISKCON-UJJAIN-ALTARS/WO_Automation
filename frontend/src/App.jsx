import { useEffect, useState } from "react";

import { CATEGORIES, findCategory, mergeFields, buildVariantInputs, loadVariantsFromBackend } from "./templateConfig";
import { generateMultiple } from "./api";
import useApiHealth from "./hooks/useApiHealth";

import StepTrail from "./components/StepTrail";
import SelectCard from "./components/SelectCard";
import BlueprintIcon from "./components/BlueprintIcon";
import DimensionField from "./components/DimensionField";
import A4ResultSheet from "./components/A4ResultSheet";

const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function App() {
  const [step, setStep] = useState(1); // 1 = categories (multi), 2 = components per category (multi), 3 = form/result

  // Live template/variant/field data, fetched from GET /templates rather
  // than hardcoded — see templateConfig.js's loadVariantsFromBackend().
  // Shape: { [categoryKey]: [ { key, label, sub, icon, wired, fields }, ... ] }
  const [variants, setVariants] = useState({});
  const [variantsLoadError, setVariantsLoadError] = useState(null);

  // Step 1: which categories the user checked (order = selection order, so
  // "configure Ceiling first, then Base Box" is preserved into step 2).
  const [selectedCategoryKeys, setSelectedCategoryKeys] = useState([]);

  // Step 2: one or more chosen variants ("components") PER category, e.g.
  // { ceiling: [<3dome obj>], basebox: [<back_side obj>, <bottom_side obj>] }
  const [variantSelections, setVariantSelections] = useState({});
  const [variantStepIndex, setVariantStepIndex] = useState(0);

  // Step 3: shared values keyed by field name, common fields (e.g. altar_length)
  // are entered once and reused for every selected variant that needs them.
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});

  const [submitting, setSubmitting] = useState(false);
  const [banner, setBanner] = useState(null); // { kind: 'error' | 'info', title, message }
  const [results, setResults] = useState(null); // array from generateMultiple, or null

  const { apiBase, setApiBase, status: apiStatus, checkApi } = useApiHealth(DEFAULT_API_BASE);

  // Load real template/field data from the backend once on mount. If the
  // API base is changed later, checkApi (on blur) verifies reachability,
  // but the initial variant load happens once here against the starting base.
  useEffect(() => {
    let cancelled = false;
    loadVariantsFromBackend(apiBase)
      .then((v) => {
        if (!cancelled) setVariants(v);
      })
      .catch((err) => {
        if (!cancelled) setVariantsLoadError(err.message || "Failed to load templates");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Flatten every chosen component across every selected category, in
  // selection order, e.g. [3dome_ceiling, back_side, bottom_side].
  const chosenVariants = selectedCategoryKeys.flatMap((k) => variantSelections[k] || []);
  const mergedFields = chosenVariants.length ? mergeFields(chosenVariants) : [];

  const categoryLabel = selectedCategoryKeys.map((k) => findCategory(k)?.label).filter(Boolean).join(" + ");
  const variantLabel = chosenVariants.map((v) => v.label).join(" + ");

  const currentCategoryKey = selectedCategoryKeys[variantStepIndex];
  const currentCategory = findCategory(currentCategoryKey);
  const currentCategorySelections = (currentCategoryKey && variantSelections[currentCategoryKey]) || [];

  // ── Step 1: multi-select categories ─────────────────────────────────────

  function toggleCategory(key) {
    setSelectedCategoryKeys((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  }

  function proceedFromCategories() {
    if (selectedCategoryKeys.length === 0) return;
    setVariantSelections({});
    setVariantStepIndex(0);
    setValues({});
    setErrors({});
    setBanner(null);
    setResults(null);
    setStep(2);
  }

  // ── Step 2: pick one or more components, one category at a time ─────────

  function toggleVariantForCurrent(v) {
    setVariantSelections((prev) => {
      const existing = prev[currentCategoryKey] || [];
      const already = existing.some((sel) => sel.key === v.key);
      const next = already
        ? existing.filter((sel) => sel.key !== v.key)
        : [...existing, { ...v, categoryKey: currentCategoryKey }];
      return { ...prev, [currentCategoryKey]: next };
    });
    setValues({});
    setErrors({});
    setBanner(null);
    setResults(null);
  }

  function proceedFromVariants() {
    if (currentCategorySelections.length === 0) return;
    if (variantStepIndex + 1 < selectedCategoryKeys.length) {
      setVariantStepIndex((i) => i + 1);
    } else {
      setStep(3);
    }
  }

  function goBackTo(targetStep) {
    setBanner(null);
    if (targetStep <= 1) {
      setVariantSelections({});
      setVariantStepIndex(0);
      setResults(null);
      setStep(1);
    } else if (targetStep === 2) {
      // Step back one category at a time; if already at the first
      // category's component screen, fall through to step 1. Selections
      // already made are kept, so nothing needs re-picking.
      setResults(null);
      if (variantStepIndex === 0) {
        setStep(1);
      } else {
        setVariantStepIndex((i) => i - 1);
        setStep(2);
      }
    }
  }

  // ── Step 3: merged dimension form ───────────────────────────────────────

  function handleFieldChange(key, raw) {
    setValues((prev) => ({ ...prev, [key]: raw }));
    setErrors((prev) => ({ ...prev, [key]: null }));
  }

  function validate() {
    const nextErrors = {};
    const finalValues = {};
    let ok = true;

    mergedFields.forEach((f) => {
      const raw = (values[f.key] ?? "").toString().trim();
      if (raw === "") {
        nextErrors[f.key] = "Required";
        ok = false;
        return;
      }

      // Only "number" fields get numeric coercion/validation. "text" fields
      // (e.g. box_design) and "select" fields (e.g. level_count, arch_ratio
      // options) pass through as their raw string value — running Number()
      // on something like "standard" would always fail as NaN even though
      // it's a perfectly valid value for that field.
      if (f.type === "number" || f.type === undefined) {
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
        finalValues[f.key] = num;
      } else {
        finalValues[f.key] = raw;
      }
    });

    setErrors(nextErrors);
    return ok ? finalValues : null;
  }

  async function handleSubmit() {
    setBanner(null);

    // Every variant returned by GET /templates already has a real backend
    // config entry (that's what the endpoint lists), so `wired` is always
    // true here now. Kept the split for safety in case that ever changes.
    const unwired = chosenVariants.filter((v) => !v.wired);
    const wired = chosenVariants.filter((v) => v.wired);

    const finalValues = validate();
    if (!finalValues) return;

    if (unwired.length > 0) {
      setBanner({
        kind: "info",
        title: "Some selections aren't wired up yet",
        message: `${unwired
          .map((v) => `"${v.key}"`)
          .join(", ")} has no matching backend config yet, so only the remaining selection${
          wired.length > 1 ? "s" : ""
        } will be generated.`,
      });
    }

    if (wired.length === 0) return;

    setSubmitting(true);
    try {
      const jobs = wired.map((v) => ({
        templateKey: v.key,
        label: `${findCategory(v.categoryKey)?.label ?? ""} · ${v.label}`,
        inputs: buildVariantInputs(v, finalValues),
      }));
      const outcomes = await generateMultiple(apiBase, jobs);
      setResults(outcomes);

      const failed = outcomes.filter((o) => !o.success);
      if (failed.length > 0) {
        setBanner({
          kind: "error",
          title: `${failed.length} of ${outcomes.length} drawing(s) failed to generate`,
          message: failed
            .map((f) => `${f.label}: ${f.error?.message || "unknown error"}`)
            .join("  |  "),
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

      {variantsLoadError && (
        <div className="banner">
          <strong>Couldn't load templates from the backend</strong>
          {variantsLoadError} — check the API base above and that the server is running.
        </div>
      )}

      <StepTrail step={step} categoryLabel={categoryLabel} variantLabel={variantLabel} />

      {step === 1 && (
        <section className="panel">
          <div className="panel-head">
            <h2>What are you cutting?</h2>
            <span className="tag">Step 1 of 3 · pick one or both</span>
          </div>
          <div className="panel-body">
            <div className="card-grid">
              {CATEGORIES.map((c) => (
                <SelectCard
                  key={c.key}
                  icon={c.icon}
                  title={c.label}
                  subtitle={c.blurb}
                  multi
                  selected={selectedCategoryKeys.includes(c.key)}
                  onClick={() => toggleCategory(c.key)}
                />
              ))}
            </div>
            <div className="submit-row">
              <button
                className="submit-btn"
                disabled={selectedCategoryKeys.length === 0}
                onClick={proceedFromCategories}
              >
                Continue{selectedCategoryKeys.length > 0 ? ` with ${categoryLabel}` : ""}
              </button>
            </div>
          </div>
        </section>
      )}

      {step === 2 && currentCategory && (
        <section className="panel">
          <div className="panel-head">
            <h2>Choose {currentCategory.label} component(s)</h2>
            <span className="tag">
              Step 2 of 3 · {variantStepIndex + 1} of {selectedCategoryKeys.length}
            </span>
          </div>
          <div className="panel-body">
            <button className="back-link" onClick={() => goBackTo(2)}>
              ← Back
            </button>
            {selectedCategoryKeys.length > 1 && (
              <p className="a4-actions-hint">
                Configuring {currentCategory.label} now — you'll configure{" "}
                {selectedCategoryKeys
                  .slice(variantStepIndex + 1)
                  .map((k) => findCategory(k)?.label)
                  .join(" and ") || "nothing else"}{" "}
                next.
              </p>
            )}
            <div className="card-grid">
              {(variants[currentCategory.key] || []).map((v) => (
                <SelectCard
                  key={v.key}
                  icon={v.icon}
                  title={v.label}
                  subtitle={v.sub}
                  disabledNote={v.wired ? null : "No config yet"}
                  multi
                  selected={currentCategorySelections.some((sel) => sel.key === v.key)}
                  onClick={() => toggleVariantForCurrent(v)}
                />
              ))}
              {!variantsLoadError && (variants[currentCategory.key] || []).length === 0 && (
                <p className="a4-actions-hint">Loading components…</p>
              )}
            </div>
            <div className="submit-row">
              <button
                className="submit-btn"
                disabled={currentCategorySelections.length === 0}
                onClick={proceedFromVariants}
              >
                Continue
                {currentCategorySelections.length > 0
                  ? ` with ${currentCategorySelections.map((v) => v.label).join(" + ")}`
                  : ""}
              </button>
            </div>
          </div>
        </section>
      )}

      {step === 3 && chosenVariants.length > 0 && (
        <div className="grid-2col">
          <section className="panel">
            <div className="panel-head">
              <h2>Altar Dimensions</h2>
              <span className="tag">{chosenVariants.some((v) => v.wired) ? "Input · Sheet" : "No sheet mapped"}</span>
            </div>
            <div className="panel-body">
              <button className="back-link" onClick={() => goBackTo(2)}>
                ← Back to components
              </button>

              {chosenVariants.map((v) => (
                <div className="variant-summary" key={v.key}>
                  <BlueprintIcon kind={v.icon} size={40} />
                  <div>
                    <div className="variant-summary-title">
                      {findCategory(v.categoryKey)?.label} · {v.label}
                    </div>
                    <div className="variant-summary-sub">{v.sub}</div>
                  </div>
                </div>
              ))}

              {banner && (
                <div className={`banner ${banner.kind === "info" ? "info" : ""}`}>
                  <strong>{banner.title}</strong>
                  {banner.message}
                </div>
              )}

              <form onSubmit={(e) => e.preventDefault()}>
                {mergedFields.map((f) => (
                  <DimensionField
                    key={f.key}
                    field={f}
                    value={values[f.key] ?? ""}
                    error={errors[f.key]}
                    onChange={handleFieldChange}
                    hint={f.usedBy.length > 1 ? "shared" : null}
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
                    `Generate Drawing${chosenVariants.length > 1 ? "s" : ""}`
                  )}
                </button>
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Generated Drawing{chosenVariants.length > 1 ? "s" : ""}</h2>
              <span className="tag">{results ? "Generated" : submitting ? "Processing…" : "Awaiting input"}</span>
            </div>
            <div className="panel-body">
              {!results && (
                <div className="result-empty">
                  <svg width="64" height="64" viewBox="0 0 64 64" fill="none" aria-hidden="true">
                    <rect x="8" y="8" width="48" height="48" stroke="#8A8A80" strokeWidth="1.5" strokeDasharray="4 4" />
                    <path d="M20 32h24M32 20v24" stroke="#8A8A80" strokeWidth="1.5" />
                  </svg>
                  <p>
                    Fill in the dimensions and generate to see every selected drawing rendered together on one
                    A4-sized sheet.
                  </p>
                </div>
              )}
              {results && <A4ResultSheet apiBase={apiBase} results={results} />}
            </div>
          </section>
        </div>
      )}

      <footer>
        <span>Google Sheets remains the source of truth — Python performs zero calculations.</span>
        <span>{chosenVariants.length ? `templates: ${chosenVariants.map((v) => v.key).join(", ")}` : "no template selected"}</span>
      </footer>
    </div>
  );
}