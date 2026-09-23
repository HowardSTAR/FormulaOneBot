import '../../components/MenuIcon.css';

// Viewports in the user-supplied 1122 × 1402 artwork, excluding text labels.
const ICON_FRAMES = {
  home: [269, 143, 103, 102], calendar: [406, 143, 103, 102],
  results: [544, 143, 103, 102], peloton: [682, 143, 103, 102],
  analytics: [820, 143, 103, 102], wiki: [958, 143, 103, 102],
  account: [269, 305, 103, 102], notifications: [406, 305, 103, 102],
  contact: [544, 305, 103, 102], games: [682, 305, 103, 102],
  admin: [820, 305, 103, 102], vote: [958, 305, 103, 102],
  favorite: [269, 462, 103, 102], settings: [406, 462, 103, 102],
  practice: [281, 671, 91, 88], sprintQuali: [417, 671, 91, 88],
  sprint: [552, 671, 91, 88], quali: [686, 671, 91, 88], race: [822, 671, 91, 88],
  drivers: [280, 861, 91, 86], teams: [416, 861, 91, 86],
  compare: [280, 1032, 91, 86], predictions: [416, 1032, 91, 86],
  predictionAnalytics: [551, 1032, 91, 86],
  reaction: [280, 1212, 91, 87], grid: [416, 1212, 91, 87], arcade: [551, 1212, 91, 87],
} as const;
export type IndexIconName = keyof typeof ICON_FRAMES;

export default function IndexIcon({name}: {name: IndexIconName}) {
  return <span className={`menu-icon index-menu-icon is-${name}`} aria-hidden="true">
    <svg className="index-icon-artwork" viewBox={ICON_FRAMES[name].join(' ')} focusable="false">
      <image href="/f1hub-navigation-20260923.png" width="1122" height="1402" />
    </svg>
  </span>;
}
