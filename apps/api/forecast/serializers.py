from rest_framework import serializers
from forecast.models import Holiday


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = [
            "id", "name", "date", "scope",
            "demand_multiplier", "pre_days", "pre_multiplier",
            "is_recurring",
        ]
        read_only_fields = ["id"]
