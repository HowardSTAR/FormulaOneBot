import { lazy, Suspense } from "react";
import { createBrowserRouter } from "react-router-dom";
import { SwipeBackLayout } from "./components/SwipeBackLayout";
import { RequirePersonalAccount } from "./components/RequirePersonalAccount";
import IndexPage from "./pages/index/Index";
import { RequireAdmin } from "./components/RequireAdmin";

// Keep only the home screen eager: charts, games and other page-specific code
// and styles must not be downloaded/evaluated just to open the website.
const ComparePage = lazy(() => import("./pages/compare/ComparePage"));
const ConstructorsPage = lazy(() => import("./pages/constructors/ConstructorsPage"));
const ConstructorDetailsPage = lazy(() => import("./pages/constructor-details/ConstructorDetailsPage"));
const TeamPrincipalPage = lazy(() => import("./pages/team-principal/TeamPrincipalPage"));
const DriverDetailsPage = lazy(() => import("./pages/driver-details/DriverDetailsPage"));
const DriversPage = lazy(() => import("./pages/drivers/DriversPage"));
const HistoryPage = lazy(() => import("./pages/history/HistoryPage"));
const FavoritesPage = lazy(() => import("./pages/favorites/FavoritesPage"));
const NextRacePage = lazy(() => import("./pages/next-race/NextRacePage"));
const QualiResultsPage = lazy(() => import("./pages/quali-results/QualiResultsPage"));
const RaceDetailsPage = lazy(() => import("./pages/race-details/RaceDetailsPage"));
const RaceResultsPage = lazy(() => import("./pages/race-results/RaceResultsPage"));
const SettingsPage = lazy(() => import("./pages/settings/SettingsPage"));
const SeasonPage = lazy(() => import("./pages/season/SeasonPage"));
const SprintQualiResultsPage = lazy(() => import("./pages/sprint-quali-results/SprintQualiResultsPage"));
const SprintResultsPage = lazy(() => import("./pages/sprint-results/SprintResultsPage"));
const VotingPage = lazy(() => import("./pages/voting/VotingPage"));
const AccountPage = lazy(() => import("./pages/account/AccountPage"));
const ResetPasswordPage = lazy(() => import("./pages/reset-password/ResetPasswordPage"));
const ReactionGamePage = lazy(() => import("./pages/reaction-game/ReactionGamePage"));
const ReflexGridGamePage = lazy(() => import("./pages/reflex-grid-game/ReflexGridGamePage"));
const RaceGamePage = lazy(() => import("./pages/race-game/RaceGamePage"));
const PredictionsPage = lazy(() => import("./pages/predictions/PredictionsPage"));
const PracticeResultsPage = lazy(() => import("./pages/practice-results/PracticeResultsPage"));
const ContactAdminPage = lazy(() => import("./pages/contact-admin/ContactAdminPage"));
const WikiPage = lazy(() => import("./pages/wiki/WikiPage"));
const NotificationsPage = lazy(() => import("./pages/notifications/NotificationsPage"));
const DataDeletionPage = lazy(() => import("./pages/legal/LegalPages").then(m => ({ default: m.DataDeletionPage })));
const DataSourcesPage = lazy(() => import("./pages/legal/LegalPages").then(m => ({ default: m.DataSourcesPage })));
const IntellectualPropertyPage = lazy(() => import("./pages/legal/LegalPages").then(m => ({ default: m.IntellectualPropertyPage })));
const PrivacyPage = lazy(() => import("./pages/legal/LegalPages").then(m => ({ default: m.PrivacyPage })));
const TermsPage = lazy(() => import("./pages/legal/LegalPages").then(m => ({ default: m.TermsPage })));
const AdminPage = lazy(() => import("./pages/admin/AdminPage"));
const PredictionAnalyticsPage = lazy(() => import("./pages/prediction-analytics/PredictionAnalyticsPage"));

export const router = createBrowserRouter([
  { path: "/race-game", element: <Suspense fallback={<div role="status">Загрузка игры…</div>}><RaceGamePage /></Suspense> },
  {
    element: <SwipeBackLayout />,
    children: [
      { path: "/", element: <IndexPage /> },
      { path: "/account", element: <AccountPage /> },
      { path: "/compare", element: <ComparePage /> },
      { path: "/prediction-analytics", element: <RequireAdmin><Suspense fallback={<div role="status">Загрузка аналитики…</div>}><PredictionAnalyticsPage /></Suspense></RequireAdmin> },
      { path: "/constructor-details", element: <ConstructorDetailsPage /> },
      { path: "/team-principal", element: <TeamPrincipalPage /> },
      { path: "/constructors", element: <ConstructorsPage /> },
      { path: "/driver-details", element: <DriverDetailsPage /> },
      { path: "/drivers", element: <DriversPage /> },
      { path: "/history", element: <HistoryPage /> },
      { path: "/favorites", element: <RequirePersonalAccount><FavoritesPage /></RequirePersonalAccount> },
      { path: "/next-race", element: <NextRacePage /> },
      { path: "/quali-results", element: <QualiResultsPage /> },
      { path: "/race-details", element: <RaceDetailsPage /> },
      { path: "/race-results", element: <RaceResultsPage /> },
      { path: "/reaction-game", element: <ReactionGamePage /> },
      { path: "/reflex-grid-game", element: <ReflexGridGamePage /> },
      { path: "/predictions", element: <PredictionsPage /> },
      { path: "/practice-results", element: <PracticeResultsPage /> },
      { path: "/contact-admin", element: <ContactAdminPage /> },
      { path: "/reset-password", element: <ResetPasswordPage /> },
      { path: "/settings", element: <RequirePersonalAccount requireTelegram={false}><SettingsPage /></RequirePersonalAccount> },
      { path: "/season", element: <SeasonPage /> },
      { path: "/sprint-quali-results", element: <SprintQualiResultsPage /> },
      { path: "/sprint-results", element: <SprintResultsPage /> },
      { path: "/voting", element: <RequirePersonalAccount><VotingPage /></RequirePersonalAccount> },
      { path: "/wiki", element: <WikiPage /> },
      { path: "/notifications", element: <RequirePersonalAccount requireTelegram={false}><NotificationsPage /></RequirePersonalAccount> },
      { path: "/privacy", element: <PrivacyPage /> },
      { path: "/terms", element: <TermsPage /> },
      { path: "/legal/ip", element: <IntellectualPropertyPage /> },
      { path: "/about/data", element: <DataSourcesPage /> },
      { path: "/account/delete", element: <DataDeletionPage /> },
      {
        path: "/admin",
        element: (
          <RequireAdmin>
            <Suspense fallback={<div className="admin-route-state">Загружаем панель…</div>}>
              <AdminPage />
            </Suspense>
          </RequireAdmin>
        ),
      },
    ],
  },
]);
