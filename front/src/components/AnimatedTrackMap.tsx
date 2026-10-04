import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { resolveCircuitAsset } from "../assets/circuitAsset";
import './animated-track-map.css';

type AnimatedTrackMapProps = {
  eventName: string;
  location?: string;
  season?: number;
  className: string;
  svgClassName: string;
  loadingClassName: string;
};

export function AnimatedTrackMap({
  eventName,
  location,
  season,
  className,
  svgClassName,
  loadingClassName,
}: AnimatedTrackMapProps) {
  const assetName = resolveCircuitAsset(eventName, location, season);
  const [trackState, setTrackState] = useState<{
    eventName: string;
    svg: string | null;
    error: boolean;
  }>({ eventName: "", svg: null, error: false });
  const trackContainerRef = useRef<HTMLDivElement>(null);
  const trackSvg = trackState.eventName === assetName ? trackState.svg : null;
  const trackError = trackState.eventName === assetName && trackState.error;

  useEffect(() => {
    const controller = new AbortController();

    fetch(`/static/circuit/${encodeURIComponent(assetName)}.svg`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Track map not found");
        const svg = await response.text();
        if (!controller.signal.aborted) setTrackState({ eventName: assetName, svg, error: false });
      })
      .catch(() => {
        if (!controller.signal.aborted) setTrackState({ eventName: assetName, svg: null, error: true });
      });

    return () => {
      controller.abort();
    };
  }, [assetName]);

  useLayoutEffect(() => {
    const container = trackContainerRef.current;
    if (!trackSvg || !container) return;

    container.innerHTML = trackSvg;
    const svg = container.querySelector("svg");
    if (!svg) return;

    svg.style.width = "100%";
    svg.style.height = "100%";
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

    const paths = svg.querySelectorAll("path, polyline");
    const outlineGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const fillGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    outlineGroup.classList.add("track-outline-group");
    fillGroup.classList.add("track-fill-group");
    const routes: SVGGeometryElement[] = [];

    paths.forEach((path) => {
      const subpaths = path.tagName.toLowerCase() === "path"
        ? path.getAttribute("d")?.match(/[Mm][^Mm]*/g)
        : null;
      const candidates = (subpaths ?? [null]).map((part) => {
        const route = path.cloneNode(true) as SVGGeometryElement;
        if (part) route.setAttribute("d", part);
        route.removeAttribute("fill");
        return route;
      });
      routes.push(...candidates);

      path.classList.add("track-fill");
      fillGroup.appendChild(path);
    });

    // Measure each candidate only once. The map is a static illustration, not
    // a per-frame stroke animation that repaints its filters while loading.
    let longest: SVGGeometryElement | undefined;
    let longestLength = -1;
    for (const route of routes) {
      const length = route.getTotalLength();
      if (length > longestLength) { longest = route; longestLength = length; }
    }
    const visibleRoutes = longest ? [longest] : [];
    if (eventName === "Spanish Grand Prix") {
      // The legacy Madrid SVG contains fragmented filled bands, not a route
      // centreline. Use a continuous schematic centreline in its 121 × 85 viewBox.
      const madrid = document.createElementNS("http://www.w3.org/2000/svg", "path");
      madrid.setAttribute("d", "M15 69 L10 39 Q9.5 36 7 36 L5.5 36 Q3.5 29 8 26 L34 10 Q43 5 51 9 L55 11 Q56 12 57 10 Q58 9 59 10 Q60 12 64 10 L70 8 Q72 6 76 6 Q79 6 81 4 Q82 3 84 6 Q86 9 89 7 L95 4 Q98 3 100 6 Q103 11 106 10 L113 7 Q120 5 119 14 Q118 26 111 25 Q105 25 98 20 L90 14 Q86 11 83 15 L78 21 Q77 23 73 23 L66 23 Q60 23 59 28 L59 32 Q59 34 61 37 Q56 41 50 44 Q47 45 48 51 Q49 59 43 60 L29 63 Q26 63 28 66 L29 73 Q23 76 17 76 Q16 76 15 69 Z");
      visibleRoutes.splice(0, visibleRoutes.length, madrid);
    }
    for (const border of visibleRoutes) {
      border.classList.add("track-outline", "track-route-border", "animate", "animation-complete");
      border.setAttribute("pathLength", "1");
      border.style.strokeDasharray = "1 0";
      border.style.strokeDashoffset = "0";

      const surface = border.cloneNode(true) as SVGGeometryElement;
      surface.classList.remove("track-route-border");
      surface.classList.add("track-route-surface");

      outlineGroup.append(border, surface);
    }

    svg.innerHTML = "";
    svg.appendChild(fillGroup);
    svg.appendChild(outlineGroup);
    fillGroup.querySelectorAll('.track-fill').forEach(path => path.classList.add('animate'));
  }, [trackSvg, eventName]);

  return (
    <div className={`${className} animated-track-map`} aria-hidden="true">
      {!trackSvg && !trackError && <span className={loadingClassName}>Загрузка схемы трассы…</span>}
      {trackError && <span className={loadingClassName}>Схема трассы недоступна</span>}
      <div ref={trackContainerRef} className={`${svgClassName} animated-track-svg`} />
    </div>
  );
}
