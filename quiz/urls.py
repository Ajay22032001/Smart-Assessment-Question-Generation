from django.urls import path
from . import views

app_name = 'quiz'

urlpatterns = [
    path('categories/', views.category_list, name='category_list'),
    path('categories/<int:category_id>/subcategories/', views.subcategory_list, name='subcategory_list'),
    path('subcategories/<int:subcategory_id>/settings/', views.quiz_settings, name='quiz_settings'),
    path('generate/', views.generate_questions, name='generate_questions'),
    path('generate-api/', views.generate_questions_api, name='generate_questions_api'),
    path('take/', views.quiz_take, name='quiz_take'),
    path('submit/', views.quiz_submit, name='quiz_submit'),
    path('results/<int:result_id>/', views.quiz_results, name='quiz_results'),
    path('start/', views.quiz_start, name='quiz_start'),

     # Task 14: Quiz History
    path('history/', views.quiz_history, name='history'),
    
    # Task 15: Incomplete Quizzes
    path('incomplete/', views.incomplete_quizzes, name='incomplete_quizzes'),
    path('resume/<int:quiz_id>/', views.resume_quiz, name='resume_quiz'),
    path('abandon/<int:quiz_id>/', views.abandon_quiz, name='abandon_quiz'),
    
    # Task 16: Leaderboard
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('leaderboard/toggle-privacy/', views.toggle_leaderboard_privacy, name='toggle_leaderboard_privacy'),

    # Task 17: Retake and Comparison
    path('retake/<int:result_id>/', views.retake_quiz, name='retake_quiz'),
    path('comparison/', views.quiz_comparison, name='quiz_comparison'),
    path('comparison/<str:topic>/', views.quiz_comparison, name='quiz_comparison'),
    path('attempt/<int:result_id>/', views.attempt_details, name='attempt_details'),
]
