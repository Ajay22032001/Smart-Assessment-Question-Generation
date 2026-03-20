from django.shortcuts import render, redirect
from users.models import Profile  # Import from users app
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .forms import UserRegisterForm, UserProfileForm
from quiz.models import QuizResult


def home(request):
    """Home page view - redirect logged in users to dashboard"""
    if request.user.is_authenticated:
        return redirect('dashboard')  # ya 'quiz:category_list'
    return render(request, 'home.html')

def register(request):
    """User registration view"""
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful! Welcome to Smart Assessment.')
            return redirect('dashboard')
    else:
        form = UserRegisterForm()
    return render(request, 'register.html', {'form': form})

@login_required
def edit_profile(request):
    """Edit user profile"""
    if request.method == 'POST':
        u_form = UserRegisterForm(request.POST, instance=request.user)
        p_form = UserProfileForm(request.POST, request.FILES, instance=request.user.profile)
        
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, 'Your profile has been updated!')
            return redirect('dashboard')
    else:
        u_form = UserRegisterForm(instance=request.user)
        p_form = UserProfileForm(instance=request.user.profile)
    
    context = {
        'u_form': u_form,
        'p_form': p_form
    }
    return render(request, 'edit_profile.html', context)

@login_required
def dashboard(request):
    """Main dashboard view with statistics and charts"""
    # Get user's quiz results
    quiz_results = QuizResult.objects.filter(user=request.user).select_related(
        'quiz', 'quiz__subcategory', 'quiz__subcategory__category'
    ).order_by('-created_at')
    
    # Overall statistics
    total_quizzes = quiz_results.count()
    avg_score = quiz_results.aggregate(Avg('score_percent'))['score_percent__avg'] or 0
    best_score = quiz_results.aggregate(Max('score_percent'))['score_percent__max'] or 0
    
    # Category-wise statistics for pie chart
    category_stats = {}
    for result in quiz_results:
        cat_name = result.quiz.subcategory.category.name
        category_stats[cat_name] = category_stats.get(cat_name, 0) + 1
    
    # Score trends for line chart (last 10 quizzes)
    recent_results = quiz_results[:10]
    trend_dates = [r.created_at.strftime('%Y-%m-%d') for r in recent_results]
    trend_scores = [round(r.score_percent) for r in recent_results]
    
    # Recent activity
    recent_activity = quiz_results[:5]
    
    context = {
        'total_quizzes': total_quizzes,
        'avg_score': round(avg_score, 1),
        'best_score': round(best_score),
        'category_labels': list(category_stats.keys()),
        'category_data': list(category_stats.values()),
        'trend_dates': trend_dates,
        'trend_scores': trend_scores,
        'recent_activity': recent_activity,
    }
    return render(request, 'dashboard/dashboard.html', context)