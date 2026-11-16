from django.urls import path
from . import views

app_name = 'interview'

urlpatterns = [
    path('', views.settings_view, name='settings'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('sessions/', views.create_session_view, name='create_session'),
    path('sessions/<int:session_id>/', views.session_question_view, name='session_question'),
    path('sessions/<int:session_id>/results/', views.results_view, name='results'),

    # APIs
    path('api/sessions/<int:session_id>/next-question/', views.next_question_api, name='next_question_api'),
    path('api/sessions/<int:session_id>/summary/', views.session_summary_api, name='session_summary_api'),
    path('api/questions/<int:question_id>/verify/', views.verify_question_api, name='verify_question_api'),
    path('api/session-questions/<int:session_question_id>/submit/', views.submit_question_api, name='submit_question_api'),
]
