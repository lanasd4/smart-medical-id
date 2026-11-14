from rest_framework import serializers

class ChatWithPatientSerializer(serializers.Serializer):
    patient_id  = serializers.IntegerField()
    message     = serializers.CharField()
    stream      = serializers.BooleanField(required=False, default=False)
    temperature = serializers.FloatField(required=False, default=0.2)
    num_ctx     = serializers.IntegerField(required=False, default=8192)
    num_predict = serializers.IntegerField(required=False, default=512)
