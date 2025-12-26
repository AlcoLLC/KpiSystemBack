from rest_framework import viewsets, permissions, status, generics, filters
from .models import User, Department, Position, FactoryPosition
from .serializers import UserSerializer, DepartmentSerializer, MyTokenObtainPairSerializer, PositionSerializer, FactoryUserSerializer, OfficeUserSerializer, FactoryPositionSerializer
from .permissions import IsOwnerOrAdminOrReadOnly
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.decorators import action
from .filters import UserFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

class BaseUserViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = UserFilter

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request, *args, **kwargs):
        if request.method == 'GET':
            serializer = self.get_serializer(request.user)
            return Response(serializer.data)
        elif request.method in ['PUT', 'PATCH']:
            partial = request.method == 'PATCH'
            serializer = self.get_serializer(request.user, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

class OfficeUserViewSet(BaseUserViewSet):
    queryset = User.objects.filter(factory_role__isnull=True).select_related('department', 'position').order_by('first_name', 'last_name')
    serializer_class = OfficeUserSerializer

class FactoryUserViewSet(BaseUserViewSet):
    queryset = User.objects.filter(factory_role__isnull=False).select_related('factory_position').order_by('first_name', 'last_name')
    serializer_class = FactoryUserSerializer


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all().order_by('name')
    serializer_class = DepartmentSerializer
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
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
    

class FilterableDepartmentListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        queryset = Department.objects.none()  

        if user.role in ['admin', 'ceo']:
            queryset = Department.objects.all().order_by('name')

        elif user.role == 'top_management':
            queryset = user.top_managed_departments.all().order_by('name')

        serializer = DepartmentSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class PositionViewSet(viewsets.ModelViewSet):
    queryset = Position.objects.all().order_by('name')
    serializer_class = PositionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

class FactoryPositionViewSet(viewsets.ModelViewSet):
    queryset = FactoryPosition.objects.all().order_by('name')
    serializer_class = FactoryPositionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

 
class AvailableDepartmentsForRoleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        role = request.query_params.get('role')
        queryset = Department.objects.all()

        if role == 'department_lead':
            queryset = Department.objects.filter(department_lead__isnull=True)
        elif role == 'manager':
            queryset = Department.objects.filter(manager__isnull=True)
        elif role == 'ceo':
             queryset = Department.objects.filter(ceo__isnull=True)

        serializer = DepartmentSerializer(queryset, many=True)
        return Response(serializer.data)
    