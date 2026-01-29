import { createBrowserRouter } from "react-router-dom";
import IndexPage from "./pages/index/Index";

export const router = createBrowserRouter([
    {
        path: "/",
        element: <IndexPage />,
    },
]);