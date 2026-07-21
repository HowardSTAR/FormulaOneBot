import { createBrowserRouter } from "react-router-dom";
import { SwipeBackLayout } from "./components/SwipeBackLayout";
import { RequirePersonalAccount } from "./components/RequirePersonalAccount";
import IndexPage from "./pages/index/Index";
import ComparePage from "./pages/compare/ComparePage";
import ConstructorsPage from "./pages/constructors/ConstructorsPage";
import ConstructorDetailsPage from "./pages/constructor-details/ConstructorDetailsPage";
import TeamPrincipalPage from "./pages/team-principal/TeamPrincipalPage";
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
import ResetPasswordPage from "./pages/reset-password/ResetPasswordPage";
import ReactionGamePage from "./pages/reaction-game/ReactionGamePage";
import ReflexGridGamePage from "./pages/reflex-grid-game/ReflexGridGamePage";
import PredictionsPage from "./pages/predictions/PredictionsPage";
import ContactAdminPage from "./pages/contact-admin/ContactAdminPage";

export const router = createBrowserRouter([
  {
    element: <SwipeBackLayout />,
    children: [
      { path: "/", element: <IndexPage /> },
      { path: "/account", element: <AccountPage /> },
      { path: "/compare", element: <ComparePage /> },
      { path: "/constructor-details", element: <ConstructorDetailsPage /> },
      { path: "/team-principal", element: <TeamPrincipalPage /> },
      { path: "/constructors", element: <ConstructorsPage /> },
      { path: "/driver-details", element: <DriverDetailsPage /> },
      { path: "/drivers", element: <DriversPage /> },
      { path: "/favorites", element: <RequirePersonalAccount><FavoritesPage /></RequirePersonalAccount> },
      { path: "/next-race", element: <NextRacePage /> },
      { path: "/quali-results", element: <QualiResultsPage /> },
      { path: "/race-details", element: <RaceDetailsPage /> },
      { path: "/race-results", element: <RaceResultsPage /> },
      { path: "/reaction-game", element: <ReactionGamePage /> },
      { path: "/reflex-grid-game", element: <ReflexGridGamePage /> },
      { path: "/predictions", element: <RequirePersonalAccount><PredictionsPage /></RequirePersonalAccount> },
      { path: "/contact-admin", element: <ContactAdminPage /> },
      { path: "/reset-password", element: <ResetPasswordPage /> },
      { path: "/settings", element: <RequirePersonalAccount><SettingsPage /></RequirePersonalAccount> },
      { path: "/season", element: <SeasonPage /> },
      { path: "/sprint-quali-results", element: <SprintQualiResultsPage /> },
      { path: "/sprint-results", element: <SprintResultsPage /> },
      { path: "/voting", element: <RequirePersonalAccount><VotingPage /></RequirePersonalAccount> },
    ],
  },
]);
