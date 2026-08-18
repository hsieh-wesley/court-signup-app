import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./apiClient";

const LocationCtx = createContext(null);

export function LocationProvider({ children }) {
  const [locations, setLocations] = useState([]);
  const [selectedLocationId, setSelectedLocationIdState] = useState(
    () => localStorage.getItem("locationId") || null
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getLocations().then((locs) => {
      setLocations(locs);
      setLoading(false);
      setSelectedLocationIdState((current) => {
        if (current && locs.some((l) => String(l.id) === String(current))) return current;
        return locs.length ? String(locs[0].id) : null;
      });
    });
  }, []);

  function setSelectedLocationId(id) {
    const value = id ? String(id) : null;
    setSelectedLocationIdState(value);
    if (value) localStorage.setItem("locationId", value);
    else localStorage.removeItem("locationId");
  }

  const selectedLocation =
    locations.find((l) => String(l.id) === String(selectedLocationId)) || null;

  return (
    <LocationCtx.Provider
      value={{ locations, selectedLocationId, selectedLocation, setSelectedLocationId, loading }}
    >
      {children}
    </LocationCtx.Provider>
  );
}

// Named `useFacility` (not `useLocation`) to avoid colliding with
// react-router-dom's own useLocation hook.
export function useFacility() {
  return useContext(LocationCtx);
}
