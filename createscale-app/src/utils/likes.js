// src/utils/likes.js
//
// Profile-like toggle: POST /api/users/profiles/<user_id>/like/. One
// endpoint does both like and unlike — the server checks whether a Like
// row already exists and flips it. Same endpoint the website's heart
// button calls (session auth there, token auth here).

import { API_BASE_URL } from "../config/api";

export async function toggleLike(token, userId) {
    const res = await fetch(`${API_BASE_URL}/users/profiles/${userId}/like/`, {
        method: "POST",
        headers: { Authorization: `Token ${token}` },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        const err = new Error(data.detail || "Could not update like.");
        err.status = res.status;
        throw err;
    }
    return data;
}
