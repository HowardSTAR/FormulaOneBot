import "./assets/styles.css"
import { RouterProvider } from "react-router-dom"
import { router } from "./router"
import { HeroDataProvider } from "./context/HeroDataContext"
import { ScrollToTop } from "./components/ScrollToTop"

function App() {
  return (
    <HeroDataProvider>
      <div className="root">
        <RouterProvider router={router} />
      </div>
      <ScrollToTop />
    </HeroDataProvider>
  )
}

export default App
