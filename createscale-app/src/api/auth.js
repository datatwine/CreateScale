// src/api/auth.js

// This file is a tiny "API client" layer for anything related to auth.
// Keeping it separate makes it easy to re-use across screens and to
// swap URLs or payload shapes later if your backend changes.

import { API_BASE_URL } from "../config/api";

/**
 * Log in with username + password.
 * Talks to your Django endpoint: POST /api/auth/token/
 *
 * Expected response from backend:
 *   { "token": "yourauthtoken" }
 *
 * If credentials are wrong, backend usually returns:
 *   400 with some error detail.
 */
export async function loginWithUsernamePassword(username, password) {
  const url = `${API_BASE_URL}/auth/token/`;
  console.log("Login: POST", url);

  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ username, password }),
    });
  } catch (err) {
    // This is the place where "Network request failed" originates
    console.log("Network error while calling auth/token:", err);
    throw new Error(
      "Network request failed – check API_BASE_URL and that your device can reach the backend."
    );
  }

  const data = await response.json();

  if (!response.ok) {
    const detail = data.detail || "Login failed. Check your credentials.";
    throw new Error(detail);
  }

  if (!data.token) {
    throw new Error("Login response did not contain a token.");
  }

  return data;
}


/**
 * Get current user profile (optional for now).
 * You already have /api/auth/me/ and /api/users/me/ on backend.
 * Here is a helper for /api/auth/me/.
 */
export async function fetchAuthMe(token) {
  const url = `${API_BASE_URL}/auth/me/`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "Authorization": `Token ${token}`,
    },
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || "Failed to load current user.");
  }

  return data; // { user_id, username, profile: {...} }
}

/**
 * Placeholder signup API call.
 *
 * Right now your backend doesn't expose a JSON-based signup endpoint.
 * Eventually we want something like:
 *   POST /api/auth/signup/ -> creates user and returns token/user.
 *
 * For now this just simulates a delay and "success".
 * We'll wire the real endpoint later when you add it in Django.
 */
export async function signupPlaceholder(payload) {
  // payload might contain { username, email, password1, password2, ... }

  // Fake 1 second delay so UI can show loading.
  await new Promise((resolve) => setTimeout(resolve, 1000));

  // Return a simple object so screen can display a "success" message.
  return { message: "Signup simulated. Hook this up to real API later." };
}

// ---------------------------------------------
// Fetch uploads for the currently authenticated user
// API endpoint: GET /api/users/me/uploads/
// Returns a list of uploads with fields like:
//   { id, caption, upload_date, image_url, video_url }
// ---------------------------------------------
export async function fetchMyUploads(token) {
  const url = `${API_BASE_URL}/users/me/uploads/`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      // DRF Token authentication uses the format: "Token <key>"
      Authorization: `Token ${token}`,
    },
  });

  if (!response.ok) {
    // Read the text so error messages from Django/DRF are at least visible
    const errorText = await response.text();
    console.error(
      "[fetchMyUploads] Failed:",
      response.status,
      response.statusText,
      errorText
    );
    throw new Error(
      `Failed to fetch uploads (${response.status}): ${response.statusText}`
    );
  }

  // This should be a JSON array ([])
  const data = await response.json();
  return data;
}
