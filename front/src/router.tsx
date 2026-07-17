import { Navigate, createBrowserRouter } from "react-router-dom";
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { SwipeBackLayout } from "./components/SwipeBackLayout";
import IndexPage from "./pages/index/Index";
import ComparePage from "./pages/compare/ComparePage";
import ConstructorsPage from "./pages/constructors/ConstructorsPage";
import ConstructorDetailsPage from "./pages/constructor-details/ConstructorDetailsPage";
import DriverDetailsPage from "./pages/driver-details/DriverDetailsPage";
import DriversPage from "./pages/drivers/DriversPage";
import FavoritesPage from "./pages/favorites/FavoritesPage";
import NextRacePage from "./pages/next-race/NextRacePage";
import QualiResultsPage from "./pages/quali-results/QualiResultsPage";
import RaceDetailsPage from "./pages/race-details/RaceDetailsPage";
import RaceResultsPage from "./pages/race-results/RaceResultsPage";
import SettingsPage from "./pages/settings/SettingsPage";
import SeasonPage from "./pages/season/SeasonPage";
import SprintQualiResultsPage from "./pages/sprint-quali-results/SprintQualiResultsPage";
import SprintResultsPage from "./pages/sprint-results/SprintResultsPage";
import VotingPage from "./pages/voting/VotingPage";
import AccountPage from "./pages/account/AccountPage";
import { getWebsiteUser, hasTelegramAuth } from "./helpers/auth";

function RequirePersonalAccount({ children }: { children: ReactElement }) {
  const telegramMiniApp = hasTelegramAuth();
  const [allowed, setAllowed] = useState<boolean | null>(telegramMiniApp ? true : null);

  useEffect(() => {
    if (telegramMiniApp) return;
    getWebsiteUser().then((user) => setAllowed(Boolean(user?.telegram_id)));
  }, [telegramMiniApp]);

  if (allowed === null) return null;
  return allowed ? children : <Navigate to="/account" replace />;
}

export const router = createBrowserRouter([
  {
    element: <SwipeBackLayout />,
    children: [
      { path: "/", element: <IndexPage /> },
      { path: "/account", element: <AccountPage /> },
      { path: "/compare", element: <ComparePage /> },
      { path: "/constructor-details", element: <ConstructorDetailsPage /> },
      { path: "/constructors", element: <ConstructorsPage /> },
      { path: "/driver-details", element: <DriverDetailsPage /> },
      { path: "/drivers", element: <DriversPage /> },
      { path: "/favorites", element: <RequirePersonalAccount><FavoritesPage /></RequirePersonalAccount> },
      { path: "/next-race", element: <NextRacePage /> },
      { path: "/quali-results", element: <QualiResultsPage /> },
      { path: "/race-details", element: <RaceDetailsPage /> },
      { path: "/race-results", element: <RaceResultsPage /> },
      { path: "/settings", element: <RequirePersonalAccount><SettingsPage /></RequirePersonalAccount> },
      { path: "/season", element: <SeasonPage /> },
      { path: "/sprint-quali-results", element: <SprintQualiResultsPage /> },
      { path: "/sprint-results", element: <SprintResultsPage /> },
      { path: "/voting", element: <RequirePersonalAccount><VotingPage /></RequirePersonalAccount> },
    ],
  },
]);
