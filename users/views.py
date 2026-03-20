from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.contrib.auth import logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg, Max, Sum
from .forms import RegistrationForm, UserUpdateForm, ProfileUpdateForm
from .models import Profile
from quiz.models import QuizResult, Quiz
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json

def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            try:
                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password'],
                    first_name=form.cleaned_data['full_name']
                )
                
                # Phone number update karo
                user.profile.phone = form.cleaned_data['phone']
                user.profile.save()
                
                login(request, user)
                messages.success(request, '✅ Registration successful! Welcome to Smart Assessment.')
                return redirect('dashboard')
            except Exception as e:
                messages.error(request, f'❌ Registration failed: {str(e)}')
    else:
        form = RegistrationForm()
    return render(request, 'users/register.html', {'form': form})


@login_required
def profile_edit(request):

    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=request.user.profile
        )

        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            return redirect('dashboard')

    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)

    context = {
        'u_form': u_form,
        'p_form': p_form
    }

    return render(request, 'profile/edit_profile.html', context)

def logout_user(request):
    """Logout user and redirect to home page"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')

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
    
    # Category Distribution - Top 6 categories
    category_stats = {}
    for result in quiz_results:
        cat_name = result.quiz.subcategory.category.name
        category_stats[cat_name] = category_stats.get(cat_name, 0) + 1
    
    # Sort and get top 6
    sorted_categories = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)
    top_categories = sorted_categories[:6]
    
    # Add "Others" category
    others_count = sum(count for _, count in sorted_categories[6:])
    if others_count > 0:
        top_categories.append(('Others', others_count))
    
    category_labels = [cat for cat, _ in top_categories]
    category_data = [count for _, count in top_categories]
    
    # Score Trends - Last 10 quizzes
    recent_results = list(quiz_results[:10])
    recent_results.reverse()  # Show oldest to newest
    
    trend_dates = []
    trend_scores = []
    
    for result in recent_results:
        trend_dates.append(result.created_at.strftime('%d %b'))
        trend_scores.append(round(result.score_percent))
    
    # Recent activity
    recent_activity = quiz_results[:5]
    
    # Incomplete quizzes count
    incomplete_quizzes = Quiz.objects.filter(
        status='in_progress'
    ).exclude(
        quizresult__user=request.user
    ).count()
    
    context = {
        'total_quizzes': total_quizzes,
        'avg_score': round(avg_score, 1),
        'best_score': round(best_score),
        'category_labels': json.dumps(category_labels),
        'category_data': json.dumps(category_data),
        'trend_dates': json.dumps(trend_dates),
        'trend_scores': json.dumps(trend_scores),
        'recent_activity': recent_activity,
        'incomplete_quizzes': incomplete_quizzes,
    }
    return render(request, 'users/dashboard.html', context)

@csrf_exempt
@require_POST
def tab_close_logout(request):
    """
    Tab close hone par user ko logout karo
    Refresh par ignore karo
    """
    try:
        # Request data parse karo
        data = json.loads(request.body) if request.body else {}
        action = data.get('action', 'unknown')
        username = data.get('username')
        
        print(f"📌 Tab close request: {action} for user: {username}")
        
        # Check if user is authenticated
        if request.user.is_authenticated:
            request.session.set_expiry(1)  
            
            print(f"✅ Session expiry set for: {request.user.username}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Session will expire'
            })
        else:
            print("ℹ️ User already logged out")
            return JsonResponse({
                'status': 'already_logged_out'
            })
            
    except Exception as e:
        print(f"❌ Error in tab_close_logout: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)