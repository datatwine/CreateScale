/** Mask all but the last 4 digits of a bank account number. */
export function maskAccountNumber(number) {
    if (!number) return "";
    return `****${String(number).slice(-4)}`;
}

/** Human-readable label for a Razorpay KYC status. */
export function kycLabel(status) {
    if (status === "approved") return "Approved — ready for payouts";
    if (status === "pending")  return "Pending RBI review (5-7 days)";
    if (status === "rejected") return "Rejected — please re-submit";
    return "Not set up — clients cannot pay you";
}

/** Badge colour token for a KYC status. */
export function kycColor(status) {
    if (status === "approved") return "green";
    if (status === "pending")  return "amber";
    if (status === "rejected") return "red";
    return "grey";
}
