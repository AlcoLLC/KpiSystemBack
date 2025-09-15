from rest_framework import viewsets, permissions, status, generics
from .models import User, Department
from .serializers import UserSerializer, DepartmentSerializer, MyTokenObtainPairSerializer
from .permissions import IsOwnerOrAdminOrReadOnly
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.decorators import action

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request, *args, **kwargs):
        """Get or update current user profile"""
        if request.method == 'GET':
            serializer = self.get_serializer(request.user)
            return Response(serializer.data)
        elif request.method in ['PUT', 'PATCH']:
            partial = request.method == 'PATCH'
            serializer = self.get_serializer(request.user, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated]


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


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
    
class AssignableUserListView(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if user.is_staff:
            return User.objects.filter(is_active=True).order_by('username')

        assignable_users = User.objects.none()

        assignable_users |= User.objects.filter(pk=user.pk)

        if user.role == "top_management":
            assignable_users |= User.objects.filter(role="department_lead")

        elif user.role == "department_lead":
            user_departments = Department.objects.filter(lead=user)
            if user_departments.exists():
                assignable_users |= User.objects.filter(
                    Q(department__in=user_departments, role="manager") |
                    Q(department__in=user_departments, role="employee")
                )

        elif user.role == "manager":
            user_department = user.department
            if user_department:
                assignable_users |= User.objects.filter(department=user_department, role="employee")
        
        return assignable_users.distinct().order_by('username')