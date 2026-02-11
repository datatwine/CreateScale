// src/config/api.js

import { Platform } from "react-native";

// ⚠️ CHANGE THIS to your Windows machine's LAN IP.
// Example: run `ipconfig` and look for something like 192.168.1.42
// Then use: `http://192.168.1.42/api`
const DEV_NATIVE_API_URL = "http://192.168.1.6/api";

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



