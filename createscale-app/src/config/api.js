// src/config/api.js

// IMPORTANT: This defines where your app talks to the Django API.
// For dev on your laptop, you'll likely hit your local network IP.
// Example: if your PC IP is 192.168.1.10 and Nginx listens at http://192.168.1.10/
// and Django API is under /api/, then dev URL is "http://192.168.1.10/api".

// TODO: Change this to your ACTUAL dev IP & port once you test from a phone.
// If you run the app on an Android emulator on the same machine as backend,
// you might use "http://10.0.2.2/api" instead.
const DEV_API_BASE_URL = "http://192.168.56.1/api"; // <-- CHANGE ME

// This is where your AWS / EC2 / domain will live later.
// Example: https://api.createscale.live/api
const PROD_API_BASE_URL = "https://your-production-domain.com/api";

// __DEV__ is a React Native global boolean:
// true in development, false in production builds.
export const API_BASE_URL = __DEV__ ? DEV_API_BASE_URL : PROD_API_BASE_URL;
