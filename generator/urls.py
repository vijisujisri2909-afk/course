from django.urls import path

from . import views

app_name = 'generator'

urlpatterns = [
    path('', views.generate_content, name='generate_content'),
    path('content/<int:topic_id>/', views.content_detail, name='content_detail'),
    path('students/', views.student_dashboard, name='student_dashboard'),
    path('students/content/<int:topic_id>/', views.view_content, name='view_content'),
    path('students/quiz/<int:quiz_id>/submit/', views.submit_quiz, name='submit_quiz'),
    path('students/content/<int:topic_id>/export/', views.export_pdf, name='export_pdf'),
]
