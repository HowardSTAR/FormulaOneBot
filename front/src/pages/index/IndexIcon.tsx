import { useId, type ReactNode } from "react";

type IndexIconName =
  | "quali"
  | "race"
  | "sprint"
  | "drivers"
  | "teams"
  | "compare"
  | "vote"
  | "predictions"
  | "wiki"
  | "contact"
  | "calendar"
  | "reaction"
  | "grid"
  | "arcade"
  | "favorite"
  | "settings"
  | "account";


export default function IndexIcon({ name }: { name: IndexIconName }) {
  const id = useId().replace(/:/g, "");
  const paint = `url(#${id}-paint)`;
  const metal = `url(#${id}-metal)`;
  const glass = `url(#${id}-glass)`;
  const ink = "#17212c";
  const details = { fill: "none", stroke: "#ffe9df", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const car = <><rect x="7" y="14" width="8" height="12" rx="3" fill={ink}/><rect x="33" y="14" width="8" height="12" rx="3" fill={ink}/><rect x="7" y="32" width="8" height="10" rx="3" fill={ink}/><rect x="33" y="32" width="8" height="10" rx="3" fill={ink}/><path d="M12 9h24v5H12zM17 17l4-11h6l4 11-2 17H19zM11 35h26v5H11z" fill={paint}/><path d="M20 22q4-7 8 0l-1 9h-6z" fill={glass}/><path d="M24 8v8M14 11h20M14 37h20" {...details}/></>;
  const portraits = <><path d="M7 42c0-10 7-15 17-15s17 5 17 15" fill={paint}/><circle cx="24" cy="17" r="10" fill={metal}/><path d="M17 14c2-5 9-6 13-2" {...details}/><path d="m17 29 7 8 7-8" fill={ink} opacity=".55"/></>;
  const shapes: Record<IndexIconName, ReactNode> = {
    quali: <><path d="M20 4h8v6h-8z" fill={metal}/><path d="m35 12 3-3 4 4-3 3" fill={paint}/><circle cx="24" cy="27" r="17" fill={paint}/><circle cx="24" cy="26" r="13" fill={glass} stroke="#ffcab8" strokeWidth="1.4"/><path d="M24 15v11l7 4" {...details}/><circle cx="24" cy="26" r="2.4" fill="#fff2e8"/><path d="M13 21a12 12 0 0 1 8-7" {...details}/></>,
    race: <><path d="M10 8v34" stroke={metal} strokeWidth="4" strokeLinecap="round"/><path d="M12 8c11-7 16 8 29 1v22c-13 7-18-8-29-1z" fill={metal}/><path d="M12 8v7l7-1V7zm7 6v7l7 3v-8zm7-5v7l7 2v-7zm7 9v7l8-2v-7zm-21 4v8l7-1v-8zm14 2v8l7 2v-9zm7-13v7l8-2V9z" fill={ink}/><path d="M12 8c11-7 16 8 29 1" {...details}/></>,
    sprint: <><path d="m27 3-19 25h14l-3 17 22-28H27z" fill={paint}/><path d="m27 3-5 20H8m14 5-3 17 10-23h12" fill="#fff5cc" opacity=".4"/></>,
    drivers: <><path d="M6 27C6 13 14 6 25 6c12 0 18 9 18 22v9L26 42 8 35z" fill={paint}/><path d="m8 24 34-3v11L25 35 8 30z" fill={glass}/><path d="m9 25 31-2M13 17c2-5 6-7 12-7" {...details}/><path d="m25 35 17-3v5l-16 5z" fill="#7e191f"/><circle cx="13" cy="28" r="2" fill={metal}/></>,
    teams: car,
    arcade: car,
    compare: <><path d="M7 11h27V5l10 11-10 10v-6H7z" fill={paint}/><path d="M41 29H14v-6L4 33l10 11v-6h27z" fill={metal}/><path d="M9 13h24M17 31h21" {...details}/></>,
    vote: <><path d="m7 24 7-8h22l6 8v18H7z" fill={paint}/><path d="m7 24 7-8h22l6 8z" fill="#ffb19b"/><path d="M17 22h16" stroke={ink} strokeWidth="3" strokeLinecap="round"/><rect x="18" y="5" width="16" height="18" rx="2" fill={metal} transform="rotate(12 26 14)"/><path d="m22 13 3 3 5-6" stroke="#b7212b" strokeWidth="2.5" fill="none"/><path d="m18 33 4 4 8-9" {...details}/></>,
    predictions: <><path d="M7 27h8v15H7zM20 19h8v23h-8zM33 10h8v32h-8z" fill={paint}/><path d="M7 27h3v15H7zM20 19h3v23h-3zM33 10h3v32h-3z" fill="#fff4df" opacity=".45"/><path d="m7 19 12-9 8 4L39 3m-7 0h7v7" stroke={metal} strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" fill="none"/></>,
    wiki: <><path d="M5 11q9-4 19 2 10-6 19-2v30q-10-4-19 1-10-5-19-1z" fill={paint}/><path d="M7 7q9-3 17 3 8-6 17-3v29q-9-3-17 3-8-6-17-3z" fill={metal}/><path d="M24 10v29" stroke="#986f64" strokeWidth="2"/><path d="m11 14 8 2m-8 5 8 2m10-7 8-2m-8 9 8-2" stroke="#965344" strokeWidth="1.8" strokeLinecap="round"/><path d="M31 7v15l3-3 3 2V6" fill={paint}/></>,
    calendar: <><rect x="6" y="9" width="36" height="34" rx="6" fill={paint}/><path d="M6 21h36v16a5 5 0 0 1-5 5H11a5 5 0 0 1-5-5z" fill={metal}/><path d="M15 5v10M33 5v10" stroke={metal} strokeWidth="4" strokeLinecap="round"/><path d="M14 28h4m8 0h7m-19 7h4" stroke="#986055" strokeWidth="3" strokeLinecap="round"/><rect x="25" y="32" width="9" height="7" rx="2" fill={paint}/></>,
    favorite: <><path d="m24 4 6 12 14 2-10 10 2 15-12-7-13 7 3-15L3 18l15-2z" fill={paint}/><path d="m24 4 1 20 19-6-14-2zm1 20 11 19-2-15zM3 18l22 6-14 19 3-15z" fill="#fff3b5" opacity=".65"/><path d="m24 8-5 10-10 2" {...details}/></>,
    settings: <><path d="m19 4 10 0 2 6 6 1 6 8-4 5 4 5-6 8-6 1-2 6H19l-2-6-6-1-6-8 4-5-4-5 6-8 6-1z" fill={paint}/><circle cx="24" cy="24" r="11" fill={metal}/><circle cx="24" cy="24" r="6.5" fill={glass}/><path d="m20 7 7 0m-14 8-4 6" {...details}/></>,
    account: <>{portraits}<circle cx="36" cy="35" r="10" fill={glass} stroke="#ffbba5" strokeWidth="1.5"/><path d="m31 35 3 3 6-7" {...details}/></>,
    contact: <><path d="M12 13h32v25H33l-7 7v-7H12z" fill="#7b222c"/><path d="M4 5h34v27H17L7 40v-8H4z" fill={paint}/><path d="M8 9h26" {...details}/><path d="M12 17h18M12 24h11" stroke={metal} strokeWidth="3" strokeLinecap="round"/></>,
    reaction: <><rect x="12" y="3" width="24" height="42" rx="9" fill={glass} stroke="#8caeaa" strokeWidth="1.5"/><circle cx="24" cy="12" r="5" fill="#924f54"/><circle cx="24" cy="24" r="5" fill="#a98a48"/><circle cx="24" cy="36" r="6" fill={paint}/><path d="m21 34 3-1" {...details}/></>,
    grid: <>{[[6,6],[27,6],[6,27],[27,27]].map(([x,y],i)=><g key={i}><rect x={x} y={y+2} width="16" height="16" rx="4" fill="#70481d"/><rect x={x} y={y} width="16" height="16" rx="4" fill={i===1?metal:paint}/><path d={`M${x+4} ${y+3}h8`} {...details}/></g>)}</>,
  };
  return (
    <span className={`menu-icon index-menu-icon is-${name}`} aria-hidden="true">
      <svg viewBox="0 0 48 48" focusable="false">
        <defs>
          <linearGradient id={`${id}-paint`} x1="0" y1="0" x2=".8" y2="1" gradientUnits="objectBoundingBox">
            <stop stopColor="var(--icon-light)"/><stop offset=".48" stopColor="var(--icon-color)"/><stop offset="1" stopColor="var(--icon-dark)"/>
          </linearGradient>
          <linearGradient id={`${id}-metal`} x2=".65" y2="1">
            <stop stopColor="#fff9ee"/><stop offset=".5" stopColor="#e5d6ce"/><stop offset="1" stopColor="#8b94a3"/>
          </linearGradient>
          <linearGradient id={`${id}-glass`} x2=".7" y2="1">
            <stop stopColor="#627987"/><stop offset=".45" stopColor="#233743"/><stop offset="1" stopColor="#091018"/>
          </linearGradient>
        </defs>
        <g className="index-icon-object">{shapes[name]}</g>
      </svg>
    </span>
  );
}
