from rest_framework import serializers
from bookings.models import Engagement, Review


class EngagementSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    performer = serializers.SerializerMethodField()
    already_reviewed = serializers.SerializerMethodField()
    counterpart_review = serializers.SerializerMethodField()

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
            "is_past_event",
            "already_reviewed",
            "counterpart_review",
            "created_at",
            "updated_at",
        ]

    def get_client(self, obj):
        return {"id": obj.client_id, "username": obj.client.username}

    def get_performer(self, obj):
        return {"id": obj.performer_id, "username": obj.performer.username}

    def get_already_reviewed(self, obj):
        if hasattr(obj, "is_already_reviewed"):
            return obj.is_already_reviewed

        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Review.objects.filter(engagement=obj, author=request.user).exists()

    def get_counterpart_review(self, obj):
        already_reviewed = self.get_already_reviewed(obj)
        if not already_reviewed:
            return None

        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        # Use prefetched reviews if available to prevent N+1 queries
        if (
            hasattr(obj, "_prefetched_objects_cache")
            and "reviews" in obj._prefetched_objects_cache
        ):
            for review in obj.reviews.all():
                if review.author_id != request.user.id:
                    return {
                        "rating": review.rating,
                        "comment": review.comment,
                    }
        else:
            counterpart_review = (
                Review.objects.filter(engagement=obj)
                .exclude(author=request.user)
                .first()
            )
            if counterpart_review:
                return {
                    "rating": counterpart_review.rating,
                    "comment": counterpart_review.comment,
                }
        return None


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["rating", "comment"]


class EngagementCreateSerializer(serializers.Serializer):
    date = serializers.DateField()
    time = serializers.TimeField()
    venue = serializers.CharField(max_length=255)
    occasion = serializers.CharField(max_length=255)


class EngagementActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["accept", "decline", "cancel_client", "cancel_performer"]
    )
    emergency_reason = serializers.CharField(
        required=False, allow_blank=True, default=""
    )


class VerifyPaymentSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


class DisputeSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=10, max_length=1000)


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
