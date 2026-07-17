import { createContext } from "react";
import type { HeroDataContextValue } from "./HeroDataContext";

export const HeroDataContext = createContext<HeroDataContextValue | null>(null);
