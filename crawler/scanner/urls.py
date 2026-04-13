from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from . import views

app_name = 'scanner'

urlpatterns = [
    path('', views.home_view, name='index'),
    path('history/', views.history_view, name='history'),
    path('report/<int:task_id>/', views.report_details_view, name='report_details'),
    path('download/<int:task_id>/', views.download_report_view, name='download'),
    path('api/tasks/pending/', views.pending_tasks_api, name='pending_tasks_api'),
    path('login/', LoginView.as_view(template_name='scanner/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', LogoutView.as_view(next_page='scanner:login'), name='logout'),
    path('register/', views.register_view, name='register'),
]