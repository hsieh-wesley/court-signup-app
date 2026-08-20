import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./apiClient";

const LocationCtx = createContext(null);

// A real facility never has this as its id (Location ids from the DB are
// numeric), so it's a safe sentinel for "every active facility combined"
// — used by Overview when admin hasn't (or deliberately hasn't) pinned a
// kiosk to one specific site.
export const ALL_LOCATIONS = "all";

export function LocationProvider({ children }) {
  const [locations, setLocations] = useState([]);
  const [selectedLocationId, setSelectedLocationIdState] = useState(
    () => localStorage.getItem("locationId") || ALL_LOCATIONS
  );
  const [loading, setLoading] = useState(true);

  const refreshLocations = useCallback(() => {
    return api.getLocations().then((locs) => {
      setLocations(locs);
      setLoading(false);
      setSelectedLocationIdState((current) => {
        if (current === ALL_LOCATIONS) return current;
        if (current && locs.some((l) => String(l.id) === String(current))) return current;
        // Whatever was previously selected no longer exists/is active
        // (e.g. the facility got archived) — fall back to "every
        // location" rather than silently guessing a different one.
        return ALL_LOCATIONS;
      });
    });
  }, []);

  useEffect(() => {
    refreshLocations();
  }, [refreshLocations]);

  const setSelectedLocationId = useCallback((id) => {
    const value = id ? String(id) : ALL_LOCATIONS;
    setSelectedLocationIdState(value);
    localStorage.setItem("locationId", value);
  }, []);

  const selectedLocation =
    locations.find((l) => String(l.id) === String(selectedLocationId)) || null;

  // Memoized so consumers only re-render when something they actually use
  // changes, not on every render of every other provider/component in the
  // tree (a fresh object literal here would otherwise be a "new" context
  // value on every render, forcing every useFacility() consumer to
  // re-render too).
  const value = useMemo(
    () => ({
      locations,
      selectedLocationId,
      selectedLocation,
      setSelectedLocationId,
      loading,
      refreshLocations,
    }),
    [locations, selectedLocationId, selectedLocation, setSelectedLocationId, loading, refreshLocations]
  );

  return <LocationCtx.Provider value={value}>{children}</LocationCtx.Provider>;
}

// Named `useFacility` (not `useLocation`) to avoid colliding with
// react-router-dom's own useLocation hook.
export function useFacility() {
  return useContext(LocationCtx);
}
