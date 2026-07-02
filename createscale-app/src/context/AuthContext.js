// src/context/AuthContext.js

import React, { createContext, useState, useEffect } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { loginWithUsernamePassword, fetchAuthMe } from "../api/auth";
import { isUnauthorized, AUTH_TOKEN_KEY } from "../utils/session";

// This context will be used by screens to access:
// - authState.token
// - authState.user
// - login(...) function
// - logout() function
export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // token: the auth token from Django
  // user: optional user info from /auth/me/ (not strictly required on day 1)
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);

  // loading: used while reading token from AsyncStorage on app startup
  const [initializing, setInitializing] = useState(true);

  // On first mount, try to load any saved token from AsyncStorage.
  useEffect(() => {
    (async () => {
      try {
        const storedToken = await AsyncStorage.getItem(AUTH_TOKEN_KEY);
        if (storedToken) {
          try {
            const me = await fetchAuthMe(storedToken);
            setToken(storedToken);
            setUser(me);
          } catch (err) {
            console.log("Failed to preload user:", err.message);
            if (isUnauthorized(err.status)) {
              // Token was invalidated/deleted server-side — clear it so
              // the app renders the Login stack instead of getting stuck
              // showing a "logged in" screen with no valid session.
              await AsyncStorage.removeItem(AUTH_TOKEN_KEY);
            } else {
              // Network/timeout error — keep the token, let per-screen
              // fetches surface the problem instead of forcing a logout
              // on a transient connectivity issue.
              setToken(storedToken);
            }
          }
        }
      } catch (err) {
        console.log("Failed to read token from storage:", err.message);
      } finally {
        setInitializing(false);
      }
    })();
  }, []);

  // Login function used by LoginScreen
  const login = async (username, password) => {
    // This function is intentionally thin: just calls API client
    // and stores token. Screen handles loading + error display.
    const data = await loginWithUsernamePassword(username, password);
    const newToken = data.token;

    setToken(newToken);
    await AsyncStorage.setItem(AUTH_TOKEN_KEY, newToken);

    // Optional: fetch user
    try {
      const me = await fetchAuthMe(newToken);
      setUser(me);
    } catch (err) {
      console.log("Failed to load user after login:", err.message);
    }
  };

  // Called by OAuth social login buttons — token already obtained from backend
  const loginWithToken = async (newToken) => {
    setToken(newToken);
    await AsyncStorage.setItem(AUTH_TOKEN_KEY, newToken);
    try {
      const me = await fetchAuthMe(newToken);
      setUser(me);
    } catch (err) {
      console.log("Failed to load user after OAuth login:", err.message);
    }
  };

  const logout = async () => {
    setToken(null);
    setUser(null);
    await AsyncStorage.removeItem(AUTH_TOKEN_KEY);
    // Later we can also call backend /auth/logout/ if you want.
  };

  const value = {
    token,
    user,
    initializing,
    login,
    loginWithToken,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}

