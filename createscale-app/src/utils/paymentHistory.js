import { API_BASE_URL } from "../config/api";

export function paymentStatusColor(status) {
    if (status === "paid")     return "#E68A00";
    if (status === "released") return "#2ecc71";
    if (status === "refunded") return "#e74c3c";
    return "#aaa";
}

export function paymentStatusLabel(status) {
    if (status === "paid")     return "Paid (in escrow)";
    if (status === "released") return "Released to performer";
    if (status === "refunded") return "Refunded to client";
    return "Unpaid";
}

export async function fetchPerformerPayouts(token) {
    const res = await fetch(`${API_BASE_URL}/bookings/payouts/performer/`, {
        headers: { Authorization: `Token ${token}` },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.results;
}

export async function fetchClientPayments(token) {
    const res = await fetch(`${API_BASE_URL}/bookings/payments/client/`, {
        headers: { Authorization: `Token ${token}` },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.results;
}
