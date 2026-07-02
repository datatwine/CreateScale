from rest_framework import serializers
from bookings.models import Engagement


class EngagementSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    performer = serializers.SerializerMethodField()
    payment_deadline = serializers.SerializerMethodField()

    class Meta:
        model = Engagement
        fields = [
            "id",
            "client",
            "performer",
            "date",
            "time",
            "venue",
            "occasion",
            "status",
            "client_emergency_reason",
            "performer_emergency_reason",
            "fee",
            "payment_status",
            "payment_deadline",
            "created_at",
            "updated_at",
        ]

    def get_client(self, obj):
        return {"id": obj.client_id, "username": obj.client.username}

    def get_performer(self, obj):
        return {"id": obj.performer_id, "username": obj.performer.username}

    def get_payment_deadline(self, obj):
        deadline = obj.payment_deadline()
        return deadline.isoformat() if deadline else None


class EngagementCreateSerializer(serializers.Serializer):
    date = serializers.DateField()
    time = serializers.TimeField()
    venue = serializers.CharField(max_length=255)
    occasion = serializers.CharField(max_length=255)


class EngagementActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["accept", "decline", "cancel_client", "cancel_performer"])
    emergency_reason = serializers.CharField(required=False, allow_blank=True, default="")


class PaymentHistorySerializer(serializers.ModelSerializer):
    """Shared serializer for performer payouts and client payment history."""
    client = serializers.SerializerMethodField()
    performer = serializers.SerializerMethodField()

    class Meta:
        model = Engagement
        fields = [
            "id",
            "client",
            "performer",
            "date",
            "time",
            "venue",
            "occasion",
            "fee",
            "payment_status",
            "paid_at",
            "released_at",
            "refunded_at",
        ]

    def get_client(self, obj):
        return {"id": obj.client_id, "username": obj.client.username}

    def get_performer(self, obj):
        return {"id": obj.performer_id, "username": obj.performer.username}
