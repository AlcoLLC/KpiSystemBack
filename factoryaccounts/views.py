from rest_framework import viewsets, permissions, status, generics, filters
from .models import User, Position
from .serializers import UserSerializer, MyTokenObtainPairSerializer, PositionSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related('position').order_by('first_name', 'last_name')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['role', 'factory_type']
    search_fields = ['first_name', 'last_name', 'email']

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request, *args, **kwargs):
        user = request.user
        if request.method == 'GET':
            serializer = self.get_serializer(user)
            return Response(serializer.data)
        
        partial = request.method == 'PATCH'
        serializer = self.get_serializer(user, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def factory_staff(self, request):
        if not request.user.factory_type:
            return Response({"detail": "İstifadəçinin zavod tipi təyin edilməyib."}, status=400)
            
        staff = User.objects.filter(factory_type=request.user.factory_type).exclude(id=request.user.id)
        serializer = self.get_serializer(staff, many=True)
        return Response(serializer.data)


class PositionViewSet(viewsets.ModelViewSet):
    queryset = Position.objects.all().order_by('name')
    serializer_class = PositionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request}) 
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Uğurla çıxış edildi."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response({"detail": "Yanlış token."}, status=status.HTTP_400_BAD_REQUEST)


class FactoryStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ['admin', 'top_management']:
            return Response({"detail": "İcazəniz yoxdur."}, status=403)

        data = {
            "dolum_count": User.objects.filter(factory_type='dolum').count(),
            "bidon_count": User.objects.filter(factory_type='bidon').count(),
        }
        return Response(data)