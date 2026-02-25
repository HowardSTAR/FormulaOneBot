import { useRef, useCallback } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { hapticImpact } from "../helpers/telegram";

const EDGE_THRESHOLD = 30;
const SWIPE_THRESHOLD = 60;

export function SwipeBackLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const startX = useRef(0);
  const startY = useRef(0);
  const tracking = useRef(false);

  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      const touch = e.touches[0];
      if (!touch) return;
      if (touch.clientX <= EDGE_THRESHOLD) {
        tracking.current = true;
        startX.current = touch.clientX;
        startY.current = touch.clientY;
      }
    },
    []
  );

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!tracking.current) return;
    const touch = e.touches[0];
    if (!touch) return;
    const deltaX = touch.clientX - startX.current;
    const deltaY = Math.abs(touch.clientY - startY.current);
    if (deltaX < 0 || deltaY > deltaX * 1.5) {
      tracking.current = false;
    }
  }, []);

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (!tracking.current) return;
      const touch = e.changedTouches[0];
      if (!touch) {
        tracking.current = false;
        return;
      }
      const deltaX = touch.clientX - startX.current;
      tracking.current = false;
      if (deltaX >= SWIPE_THRESHOLD && location.pathname !== "/") {
        hapticImpact("light");
        navigate(-1);
      }
    },
    [navigate, location.pathname]
  );

  return (
    <div
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      style={{ minHeight: "100%" }}
    >
      <Outlet />
    </div>
  );
}
