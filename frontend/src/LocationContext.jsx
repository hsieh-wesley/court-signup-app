import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./apiClient";

const LocationCtx = createContext(null);

export function LocationProvider({ children }) {
  const [locations, setLocations] = useState([]);
  const [selectedLocationId, setSelectedLocationIdState] = useState(
    () => localStorage.getItem("locationId") || null
  );
  const [loading, setLoading] = useState(true);

  const refreshLocations = useCallback(() => {
    return api.getLocations().then((locs) => {
      setLocations(locs);
      setLoading(false);
      setSelectedLocationIdState((current) => {
        if (current && locs.some((l) => String(l.id) === String(current))) return current;
        return locs.length ? String(locs[0].id) : null;
      });
    });
  }, []);

  useEffect(() => {
    refreshLocations();
  }, [refreshLocations]);

  const setSelectedLocationId = useCallback((id) => {
    const value = id ? String(id) : null;
    setSelectedLocationIdState(value);
    if (value) localStorage.setItem("locationId", value);
    else localStorage.removeItem("locationId");
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
