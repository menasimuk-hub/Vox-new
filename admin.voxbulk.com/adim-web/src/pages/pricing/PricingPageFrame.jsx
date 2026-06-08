import React from 'react'



export default function PricingPageFrame({ title, description, children, error, msg, actions }) {

  return (

    <div className="card pricingCard">

      <div className="pricingPageHead">

        <div className="pricingPageHeadText">

          <h2 className="cardTitle">{title}</h2>

          {description && <p className="pricingPageDesc">{description}</p>}

        </div>

        {actions && <div className="pricingPageActions">{actions}</div>}

      </div>

      <div className="cardBody">

        {error && <p className="err pricingAlert">{error}</p>}

        {msg && <p className="ok pricingAlert">{msg}</p>}

        {children}

      </div>

    </div>

  )

}



export function PricingField({ label, hint, children, wide, compact, fullRow }) {

  return (

    <label className={`pricingField${wide ? ' pricingFieldWide' : ''}${compact ? ' pricingFieldCompact' : ''}${fullRow ? ' pricingFieldFull' : ''}`}>

      <span className="pricingFieldLabel">{label}</span>

      {hint && <span className="pricingFieldHint">{hint}</span>}

      {children}

    </label>

  )

}



export function PricingLoadGate({ loading, error, title, description, onRetry, children }) {

  if (loading) return <p className="muted">Loading…</p>

  if (error) {

    return (

      <PricingPageFrame

        title={title}

        description={description}

        error={error}

        actions={

          onRetry ? (

            <button className="btn soft" type="button" onClick={() => void onRetry()}>

              Retry

            </button>

          ) : null

        }

      >

        {null}

      </PricingPageFrame>

    )

  }

  return children

}



export function PricingFormulaBox({ items }) {

  return (

    <div className="pricingFormulaBox">

      <p className="pricingFormulaTitle">How included amounts are calculated</p>

      <ul className="pricingFormulaList">

        {items.map((item) => (

          <li key={item}><code>{item}</code></li>

        ))}

      </ul>

      <p className="pricingFormulaNote">WA and CV unit prices come from <strong>Service rates</strong>. Extra minutes use <strong>Extra min £</strong> when the package is used up.</p>

    </div>

  )

}

