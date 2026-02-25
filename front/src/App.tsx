import "./assets/styles.css"
import { RouterProvider } from "react-router-dom"
import { router } from "./router"
import { HeroDataProvider } from "./context/HeroDataContext"

function App() {
  return (
    <HeroDataProvider>
      <div className="root">
        <RouterProvider router={router} />
      </div>
    </HeroDataProvider>
  )
}

export default App
