// src/config/api.js

import { Platform } from "react-native";
import Constants from "expo-constants";

// 🔧 LOCAL DEVELOPMENT SETUP
// Auto-detects the dev machine's LAN IP from Expo's own dev server host —
// the same address your phone already uses to fetch the JS bundle. No more
// hardcoding/updating an IP by hand every time it changes or a new
// developer joins.
export function resolveDevApiHost(hostUri) {
  if (!hostUri) return "localhost";
  return hostUri.split(":")[0];
}

const DEV_NATIVE_API_URL = `http://${resolveDevApiHost(Constants.expoConfig?.hostUri)}/api`;

// For Expo Web dev in a browser on the same machine, "localhost" is okay.
const DEV_WEB_API_URL = "http://localhost/api";

// Later, when you deploy Django+NGINX on AWS/EC2 behind a domain,
// just change this one line:
const PROD_API_URL = "https://your-production-domain.com/api";

// Decide which dev URL to use based on platform.
const DEV_API_URL =
  Platform.OS === "web" ? DEV_WEB_API_URL : DEV_NATIVE_API_URL;

// __DEV__ is true in Expo dev builds, false in production builds.
export const API_BASE_URL = __DEV__ ? DEV_API_URL : PROD_API_URL;

