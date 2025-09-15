from django.db.models import Q
from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.is_staff or user.role == "admin":
            return Task.objects.all().order_by('-created_at')

        return Task.objects.filter(
            Q(assignee=user) | Q(created_by=user)
        ).distinct().order_by('-created_at')


    def perform_create(self, serializer):
        creator = self.request.user
        assignee = serializer.validated_data["assignee"]

        if creator == assignee:
            serializer.save(created_by=creator, approved=True)
            return

        if assignee.role == "employee":
            if not assignee.department:
                raise ValidationError("The assigned employee does not belong to any department.")

            department = assignee.department
            designated_creator = department.manager or department.lead
            
            if not designated_creator:
                raise ValidationError(f"The department '{department.name}' has no assigned Manager or Lead.")
            
            if creator != designated_creator:
                 raise PermissionDenied(f"You are not the designated manager or lead for this employee's department.")
            
            serializer.save(created_by=designated_creator, approved=False)
            return

        elif assignee.role == "manager":
            if creator.role != "department_lead":
                raise PermissionDenied("Only Department Leads can assign tasks to Managers.")
        elif assignee.role == "department_lead":
            if creator.role != "top_management":
                raise PermissionDenied("Only Top Management can assign tasks to Department Leads.")
        elif assignee.role in ["top_management", "admin"]:
            raise PermissionDenied(f"You cannot assign tasks to a user with the role of {assignee.get_role_display()}.")

        serializer.save(created_by=creator, approved=False)