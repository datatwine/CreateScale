// src/api/upload.js
//
// 3-step presigned upload flow for gallery images and videos.
// Falls back to legacy multipart POST when presign returns 501 (local dev).

import { API_BASE_URL } from "../config/api";

/** Trim trailing slashes and build full URL — same helper used in every screen. */
function buildApiUrl(path) {
    const base = API_BASE_URL.replace(/\/+$/, "");
    const p = path.startsWith("/") ? path : `/${path}`;
    return `${base}${p}`;
}

/**
 * 3-step presigned upload flow:
 * 1. Get presigned URL from Django
 * 2. Upload file directly to R2
 * 3. Confirm upload with Django (creates DB record)
 *
 * Falls back to legacy multipart POST if presign returns 501 (local dev).
 */
export async function uploadMedia({ token, fileUri, fileName, contentType, caption = "" }) {
    // Step 1: Get presigned URL
    const presignRes = await fetch(buildApiUrl("/users/me/uploads/presign/"), {
        method: "POST",
        headers: {
            Authorization: `Token ${token}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ content_type: contentType }),
    });

    // Fallback to legacy multipart (local dev, USE_S3=0)
    if (presignRes.status === 501) {
        return legacyMultipartUpload({ token, fileUri, fileName, contentType, caption });
    }

    if (!presignRes.ok) throw new Error(`Presign failed: ${presignRes.status}`);
    const { url, key, content_type } = await presignRes.json();

    // Step 2: PUT file directly to R2
    const r2Res = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": content_type },
        body: { uri: fileUri, name: fileName, type: content_type },
    });
    if (!r2Res.ok && r2Res.status !== 204) {
        throw new Error(`R2 upload failed: ${r2Res.status}`);
    }

    // Step 3: Confirm with Django
    const confirmRes = await fetch(buildApiUrl("/users/me/uploads/"), {
        method: "POST",
        headers: {
            Authorization: `Token ${token}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ key, caption }),
    });

    if (!confirmRes.ok) throw new Error(`Confirm failed: ${confirmRes.status}`);
    return confirmRes.json();
}

/** Legacy multipart POST (fallback for local dev) */
async function legacyMultipartUpload({ token, fileUri, fileName, contentType, caption }) {
    const fieldName = contentType.startsWith("video") ? "video" : "image";
    const formData = new FormData();
    formData.append(fieldName, { uri: fileUri, name: fileName, type: contentType });
    if (caption) formData.append("caption", caption);

    const res = await fetch(buildApiUrl("/users/me/uploads/"), {
        method: "POST",
        headers: { Authorization: `Token ${token}` },
        body: formData,
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
}
