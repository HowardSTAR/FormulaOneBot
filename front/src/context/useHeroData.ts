import { useContext } from "react";
import { HeroDataContext } from "./heroDataContextObject";

export function useHeroData() {
  const context = useContext(HeroDataContext);
  if (!context) throw new Error("useHeroData must be used within HeroDataProvider");
  return context;
}
