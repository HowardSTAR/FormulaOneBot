import "./assets/styles.css"
import "./assets/desktop-conversion.css"
import "./assets/redesign.css"
import "./assets/usability.css"
import "./assets/ui-consistency.css"
import "./assets/ui-polish.css"
import "./assets/readability.css"
import "./assets/mobile-safe-area.css"
import "./assets/standings-results.css"
import { lazy, Suspense, useEffect } from 'react';
import { observeActions } from './helpers/analytics';
import { RouterProvider } from "react-router-dom"
import { router } from "./router"
import { HeroDataProvider } from "./context/HeroDataContext"
import { ScrollToTop } from "./components/ScrollToTop"

const TrophyUnlock = lazy(() => import('./components/TrophyUnlock'));

function App() {
  useEffect(observeActions, []);
  return (
    <HeroDataProvider>
      <div className="root">
        <RouterProvider router={router} />
      </div>
      <ScrollToTop />
      <Suspense fallback={null}><TrophyUnlock /></Suspense>
    </HeroDataProvider>
  )
}

export default App
