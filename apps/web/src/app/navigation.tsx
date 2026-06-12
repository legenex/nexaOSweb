import { createContext, useContext } from 'react';

// Lets a deep nested card switch the active tab, for example Execute linking into Projects.
export const NavigationContext = createContext<(tab: string) => void>(() => {});

export function useNavigation(): (tab: string) => void {
  return useContext(NavigationContext);
}
