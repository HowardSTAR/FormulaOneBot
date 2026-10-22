import { useState, useEffect } from "react"

const SCROLL_THRESHOLD = 300

export function ScrollToTop() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const onScroll = () => {
      setVisible(window.scrollY > SCROLL_THRESHOLD)
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  const scrollToTop = () => {
    document.getElementById('page-content')?.focus({ preventScroll: true })
    window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  }

  if (!visible) return null

  return (
    <button
      type="button"
      className="scroll-to-top"
      onClick={scrollToTop}
      aria-label="Прокрутить вверх"
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 20V4m-7 7 7-7 7 7" /></svg>
    </button>
  )
}
