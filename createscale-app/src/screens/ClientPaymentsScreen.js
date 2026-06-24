import React, { useEffect, useState } from "react";
import {
    ActivityIndicator,
    FlatList,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useNavigation } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { fetchClientPayments, paymentStatusColor } from "../utils/paymentHistory";

function PaymentRow({ item }) {
    const statusColor = paymentStatusColor(item.payment_status);
    return (
        <View style={styles.row}>
            <View style={styles.rowHeader}>
                <Text style={styles.performerName}>{item.performer?.username ?? "—"}</Text>
                <Text style={[styles.badge, { color: statusColor }]}>
                    {item.payment_status}
                </Text>
            </View>
            <Text style={styles.rowMeta}>{item.occasion} · {item.venue}</Text>
            <Text style={styles.rowMeta}>{item.date}</Text>
            <Text style={styles.feeText}>₹{item.fee ?? "—"}</Text>
        </View>
    );
}

export function ClientPaymentsScreen() {
    const navigation = useNavigation();
    const insets = useSafeAreaInsets();
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        (async () => {
            try {
                const token = await AsyncStorage.getItem("authToken");
                setData(await fetchClientPayments(token));
            } catch (e) {
                setError(e.message);
            } finally {
                setLoading(false);
            }
        })();
    }, []);

    return (
        <View style={[styles.container, { paddingTop: insets.top }]}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
                    <Text style={styles.backText}>←</Text>
                </TouchableOpacity>
                <Text style={styles.title}>Payment History</Text>
            </View>

            {loading && <ActivityIndicator color="#E68A00" style={{ marginTop: 32 }} />}
            {error && <Text style={styles.errorText}>{error}</Text>}

            {!loading && !error && data.length === 0 && (
                <Text style={styles.emptyText}>No payments made yet.</Text>
            )}

            <FlatList
                data={data}
                keyExtractor={(item) => String(item.id)}
                renderItem={({ item }) => <PaymentRow item={item} />}
                contentContainerStyle={styles.list}
            />
        </View>
    );
}

export default ClientPaymentsScreen;

const styles = StyleSheet.create({
    container:     { flex: 1, backgroundColor: "#0B0F1A" },
    header:        { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: "#1E2740" },
    backBtn:       { marginRight: 12 },
    backText:      { color: "#E68A00", fontSize: 20 },
    title:         { color: "#fff", fontSize: 18, fontWeight: "700" },
    list:          { padding: 16, paddingBottom: 32 },
    row:           { backgroundColor: "#13192B", borderRadius: 10, padding: 14, marginBottom: 12 },
    rowHeader:     { flexDirection: "row", justifyContent: "space-between", marginBottom: 4 },
    performerName: { color: "#fff", fontWeight: "600", fontSize: 15 },
    badge:         { fontSize: 13, fontWeight: "600", textTransform: "capitalize" },
    rowMeta:       { color: "#8B95B0", fontSize: 13, marginTop: 2 },
    feeText:       { color: "#E68A00", fontSize: 15, fontWeight: "700", marginTop: 8 },
    emptyText:     { color: "#8B95B0", textAlign: "center", marginTop: 48, fontSize: 15 },
    errorText:     { color: "#e74c3c", textAlign: "center", marginTop: 32 },
});
