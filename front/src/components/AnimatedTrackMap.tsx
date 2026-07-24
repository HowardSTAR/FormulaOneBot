import { useEffect, useLayoutEffect, useRef, useState } from "react";

type AnimatedTrackMapProps = {
  eventName: string;
  className: string;
  svgClassName: string;
  loadingClassName: string;
};

function createRouteSegments(source: SVGElement) {
  const pathData = source.tagName.toLowerCase() === "path" ? source.getAttribute("d") : null;
  const subpaths = pathData?.match(/[Mm][^Mm]*/g)?.map((part) => part.trim()).filter(Boolean);
  const segments = subpaths?.length ? subpaths : [null];

  return segments.map((subpath) => {
    const route = source.cloneNode(true) as SVGGeometryElement;
    if (subpath) route.setAttribute("d", subpath);
    route.removeAttribute("fill");

    const length = route.getTotalLength?.() ?? 0;

    return { route, length };
  });
}

export function AnimatedTrackMap({
  eventName,
  className,
  svgClassName,
  loadingClassName,
}: AnimatedTrackMapProps) {
  const [trackState, setTrackState] = useState<{
    eventName: string;
    svg: string | null;
    error: boolean;
  }>({ eventName: "", svg: null, error: false });
  const trackContainerRef = useRef<HTMLDivElement>(null);
  const trackSvg = trackState.eventName === eventName ? trackState.svg : null;
  const trackError = trackState.eventName === eventName && trackState.error;

  useEffect(() => {
    let cancelled = false;

    fetch(`/static/circuit/${eventName}.svg`)
      .then(async (response) => {
        if (!response.ok) throw new Error("Track map not found");
        const svg = await response.text();
        if (!cancelled) setTrackState({ eventName, svg, error: false });
      })
      .catch(() => {
        if (!cancelled) setTrackState({ eventName, svg: null, error: true });
      });

    return () => {
      cancelled = true;
    };
  }, [eventName]);

  useLayoutEffect(() => {
    const container = trackContainerRef.current;
    if (!trackSvg || !container) return;

    const animationFrameIds: number[] = [];
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
    const routeSegments: ReturnType<typeof createRouteSegments> = [];

    paths.forEach((path) => {
      routeSegments.push(...createRouteSegments(path));

      path.classList.add("track-fill");
      fillGroup.appendChild(path);
    });

    const primaryRoute = routeSegments.reduce<(typeof routeSegments)[number] | null>(
      (longest, candidate) => (!longest || candidate.length > longest.length ? candidate : longest),
      null,
    );

    if (primaryRoute) {
      const border = primaryRoute.route;
      border.classList.add("track-outline", "track-route-border");
      border.setAttribute("pathLength", "1");
      border.dataset.trackLength = "1";
      border.style.strokeDasharray = "0 1";
      border.style.strokeDashoffset = "0";

      const surface = border.cloneNode(true) as SVGGeometryElement;
      surface.classList.remove("track-route-border");
      surface.classList.add("track-route-surface");

      outlineGroup.append(border, surface);
    }

    svg.innerHTML = "";
    svg.appendChild(fillGroup);
    svg.appendChild(outlineGroup);
    svg.getBoundingClientRect();

    const prepareFrame = window.requestAnimationFrame(() => {
      const startFrame = window.requestAnimationFrame(() => {
        const outlines = outlineGroup.querySelectorAll<SVGElement>(".track-outline");
        outlines.forEach((path) => {
          path.classList.add("animate");
          const length = path.dataset.trackLength;
          if (length) path.style.strokeDasharray = `${length} 0`;
        });
        fillGroup.querySelectorAll(".track-fill").forEach((path) => path.classList.add("animate"));
      });
      animationFrameIds.push(startFrame);
    });
    animationFrameIds.push(prepareFrame);

    return () => {
      animationFrameIds.forEach((id) => window.cancelAnimationFrame(id));
    };
  }, [trackSvg]);

  return (
    <div className={`${className} animated-track-map`} aria-hidden="true">
      {!trackSvg && !trackError && <span className={loadingClassName}>Загрузка схемы трассы…</span>}
      {trackError && <span className={loadingClassName}>Схема трассы недоступна</span>}
      <div ref={trackContainerRef} className={`${svgClassName} animated-track-svg`} />
    </div>
  );
}
