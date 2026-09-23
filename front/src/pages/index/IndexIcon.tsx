import '../../components/MenuIcon.css';
import home from '../../assets/navigation/home.png';
import calendar from '../../assets/navigation/calendar.png';
import results from '../../assets/navigation/results.png';
import peloton from '../../assets/navigation/peloton.png';
import analytics from '../../assets/navigation/analytics.png';
import wiki from '../../assets/navigation/wiki.png';
import account from '../../assets/navigation/account.png';
import notifications from '../../assets/navigation/notifications.png';
import contact from '../../assets/navigation/contact.png';
import games from '../../assets/navigation/games.png';
import admin from '../../assets/navigation/admin.png';
import vote from '../../assets/navigation/vote.png';
import favorite from '../../assets/navigation/favorite.png';
import settings from '../../assets/navigation/settings.png';
import practice from '../../assets/navigation/practice.png';
import sprintQuali from '../../assets/navigation/sprintQuali.png';
import sprint from '../../assets/navigation/sprint.png';
import quali from '../../assets/navigation/quali.png';
import race from '../../assets/navigation/race.png';
import drivers from '../../assets/navigation/drivers.png';
import teams from '../../assets/navigation/teams.png';
import compare from '../../assets/navigation/compare.png';
import predictions from '../../assets/navigation/predictions.png';
import predictionAnalytics from '../../assets/navigation/predictionAnalytics.png';
import reaction from '../../assets/navigation/reaction.png';
import grid from '../../assets/navigation/grid.png';
import arcade from '../../assets/navigation/arcade.png';

const ICONS = {
  home, calendar, results, peloton, analytics, wiki, account, notifications, contact, games, admin, vote, favorite, settings, practice, sprintQuali, sprint, quali, race, drivers, teams, compare, predictions, predictionAnalytics, reaction, grid, arcade,
} as const;
export type IndexIconName = keyof typeof ICONS;

export default function IndexIcon({name}: {name: IndexIconName}) {
  return <span className={`menu-icon index-menu-icon is-${name}`} aria-hidden="true">
    <img className="index-icon-artwork" src={ICONS[name]} alt="" decoding="async" />
  </span>;
}
