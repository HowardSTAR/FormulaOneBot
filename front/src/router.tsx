import { createBrowserRouter } from "react-router-dom";
import { SwipeBackLayout } from "./components/SwipeBackLayout";
import IndexPage from "./pages/index/Index";
import ComparePage from "./pages/compare/ComparePage";
import ConstructorsPage from "./pages/constructors/ConstructorsPage";
import DriversPage from "./pages/drivers/DriversPage";
import FavoritesPage from "./pages/favorites/FavoritesPage";
import NextRacePage from "./pages/next-race/NextRacePage";
import QualiResultsPage from "./pages/quali-results/QualiResultsPage";
import RaceDetailsPage from "./pages/race-details/RaceDetailsPage";
import RaceResultsPage from "./pages/race-results/RaceResultsPage";
import SettingsPage from "./pages/settings/SettingsPage";
import SeasonPage from "./pages/season/SeasonPage";
import VotingPage from "./pages/voting/VotingPage";

export const router = createBrowserRouter([
  {
    element: <SwipeBackLayout />,
    children: [
      { path: "/", element: <IndexPage /> },
      { path: "/compare", element: <ComparePage /> },
      { path: "/constructors", element: <ConstructorsPage /> },
      { path: "/drivers", element: <DriversPage /> },
      { path: "/favorites", element: <FavoritesPage /> },
      { path: "/next-race", element: <NextRacePage /> },
      { path: "/quali-results", element: <QualiResultsPage /> },
      { path: "/race-details", element: <RaceDetailsPage /> },
      { path: "/race-results", element: <RaceResultsPage /> },
      { path: "/settings", element: <SettingsPage /> },
      { path: "/season", element: <SeasonPage /> },
      { path: "/voting", element: <VotingPage /> },
    ],
  },
]);
