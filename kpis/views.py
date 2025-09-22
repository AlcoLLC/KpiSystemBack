from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import KPIEvaluation
from .serializers import KPIEvaluationSerializer
from .utils import send_kpi_evaluation_request_email
import logging

logger = logging.getLogger(__name__)

class KPIEvaluationViewSet(viewsets.ModelViewSet):
    queryset = KPIEvaluation.objects.all()
    serializer_class = KPIEvaluationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Kullanıcının sadece kendi değerlendirmelerini görmesini sağla
        return KPIEvaluation.objects.filter(
            models.Q(evaluator=self.request.user) | 
            models.Q(evaluatee=self.request.user)
        )

    @action(detail=False, methods=['post'])
    def self_evaluate(self, request):
        """Kullanıcının kendi kendini değerlendirmesi"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Evaluator ve evaluatee'yi aynı user olarak set et
        serializer.validated_data['evaluator'] = request.user
        serializer.validated_data['evaluatee'] = request.user
        serializer.validated_data['evaluation_type'] = KPIEvaluation.EvaluationType.SELF_EVALUATION
        
        evaluation = serializer.save()
        
        # Üst role e-posta gönder
        try:
            send_kpi_evaluation_request_email(evaluation)
            logger.info(f"Self evaluation completed and email sent for evaluation ID: {evaluation.id}")
        except Exception as e:
            logger.error(f"Email sending failed for evaluation ID: {evaluation.id}: {str(e)}")
            
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def superior_evaluate(self, request, pk=None):
        """Üst rolün değerlendirmesi"""
        evaluation = get_object_or_404(KPIEvaluation, pk=pk)
        
        # Sadece üst rol değerlendirme yapabilir
        superior = evaluation.evaluatee.get_superior()
        if not superior or superior != request.user:
            return Response(
                {"error": "Bu değerlendirmeyi sadece ilgili kullanıcının üst rolü yapabilir."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Superior evaluation olarak güncelle
        data = request.data.copy()
        data['evaluation_type'] = KPIEvaluation.EvaluationType.SUPERIOR_EVALUATION
        
        serializer = self.get_serializer(evaluation, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_evaluation = serializer.save()
        
        logger.info(f"Superior evaluation completed for evaluation ID: {evaluation.id}")
        
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def pending_evaluations(self, request):
        """Üst rolün bekleyen değerlendirmeleri"""
        # Bu kullanıcının astı olan kişilerin bekleyen değerlendirmeleri
        pending = KPIEvaluation.objects.filter(
            evaluatee__superior=request.user,
            is_superior_evaluated=False,
            self_evaluation_score__isnull=False  # Self evaluation tamamlanmış olanlar
        )
        
        serializer = self.get_serializer(pending, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_evaluations(self, request):
        """Kullanıcının kendi değerlendirmeleri"""
        evaluations = KPIEvaluation.objects.filter(evaluatee=request.user)
        serializer = self.get_serializer(evaluations, many=True)
        return Response(serializer.data)
