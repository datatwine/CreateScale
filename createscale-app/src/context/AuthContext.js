// src/context/AuthContext.js

import React, { createContext, useState, useEffect } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { loginWithUsernamePassword, fetchAuthMe } from "../api/auth";

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
        const storedToken = await AsyncStorage.getItem("@auth_token");
        if (storedToken) {
          setToken(storedToken);

          // Optional: preload user
          try {
            const me = await fetchAuthMe(storedToken);
            setUser(me);
          } catch (err) {
            console.log("Failed to preload user:", err.message);
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
    await AsyncStorage.setItem("@auth_token", newToken);

    // Optional: fetch user
    try {
      const me = await fetchAuthMe(newToken);
      setUser(me);
    } catch (err) {
      console.log("Failed to load user after login:", err.message);
    }
  };

  const logout = async () => {
    setToken(null);
    setUser(null);
    await AsyncStorage.removeItem("@auth_token");
    // Later we can also call backend /auth/logout/ if you want.
  };

  const value = {
    token,
    user,
    initializing,
    login,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}
