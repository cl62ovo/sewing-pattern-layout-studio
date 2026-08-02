import { useState } from 'react'
import { LayoutTemplate, Scissors, Sparkles } from 'lucide-react'

import { PatternStudio } from './PatternStudio'

type ProductTab = 'pattern' | 'layout'

export function App() {
  const [activeTab, setActiveTab] = useState<ProductTab>('pattern')

  return (
    <div className="product-shell">
      <header className="product-header">
        <a className="product-brand" href="#pattern" onClick={() => setActiveTab('pattern')}>
          <span><Scissors size={19} /></span>
          <strong>Plush Pattern Studio</strong>
        </a>
        <div className="product-tabs" role="tablist" aria-label="Studio tools">
          <button
            type="button"
            role="tab"
            id="pattern-tab"
            aria-controls="pattern-panel"
            aria-selected={activeTab === 'pattern'}
            className={activeTab === 'pattern' ? 'active' : ''}
            onClick={() => setActiveTab('pattern')}
          >
            <Sparkles size={17} />
            <span><strong>Pattern Studio</strong><small>3D to sewing pattern</small></span>
          </button>
          <button
            type="button"
            role="tab"
            id="layout-tab"
            aria-controls="layout-panel"
            aria-selected={activeTab === 'layout'}
            className={activeTab === 'layout' ? 'active' : ''}
            onClick={() => setActiveTab('layout')}
          >
            <LayoutTemplate size={17} />
            <span><strong>Nest & Cut</strong><small>Fabric layout</small></span>
          </button>
        </div>
        <span className="experimental-label">Experimental</span>
      </header>

      <section
        id="pattern-panel"
        role="tabpanel"
        aria-labelledby="pattern-tab"
        hidden={activeTab !== 'pattern'}
      >
        <PatternStudio />
      </section>

      <section
        id="layout-panel"
        className="legacy-panel"
        role="tabpanel"
        aria-labelledby="layout-tab"
        hidden={activeTab !== 'layout'}
      >
        {activeTab === 'layout' && (
          <iframe
            className="legacy-frame"
            src="/legacy/index.html"
            title="Nest & Cut fabric layout"
          />
        )}
      </section>
    </div>
  )
}