from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q, Count, Avg, Max, Min
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from datetime import datetime
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Category, SubCategory
import json
import logging
from django.shortcuts import render
from django.contrib.auth.models import User
from .models import QuizResult
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
import uuid  # ✅ For generating unique IDs

from .models import (
    Category, 
    SubCategory, 
    Quiz, 
    Question, 
    QuizResult, 
    UserAnswer,
    QuestionAttempt  # ✅ YEH IMPORT KARNA ZAROORI HAI
)
from .forms import QuizConfigForm
from .gemini_service import generate_questions as gen_questions, generate_explanation

logger = logging.getLogger(__name__)

@login_required
def category_list(request):
    categories = Category.objects.all()
    if not categories.exists():
        messages.info(request, 'No quiz categories are available yet.')
    return render(request, 'quiz/category_list.html', {'categories': categories})

@login_required
def subcategory_list(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    subcategories = category.subcategories.all()
    if not subcategories.exists():
        messages.warning(request, 'No subcategories are available for this category.')
    return render(request, 'quiz/subcategory_list.html', {
        'category': category,
        'subcategories': subcategories
    })


@login_required
def quiz_settings(request, subcategory_id):
    subcategory = get_object_or_404(SubCategory, id=subcategory_id)
    category = subcategory.category

    if request.method == 'POST':
        form = QuizConfigForm(request.POST)
        if form.is_valid():
            difficulty = form.cleaned_data['difficulty']
            question_count = int(form.cleaned_data['question_count'])
            timer_enabled = form.cleaned_data['timer_enabled']
            timer_duration_seconds = 60 if timer_enabled else 0

            request.session['quiz_settings'] = {
                'category_id': category.id,
                'subcategory_id': subcategory.id,
                'subcategory_name': subcategory.name,
                'difficulty': difficulty,
                'question_count': question_count,
                'timer_enabled': timer_enabled,
                'timer_duration_seconds': timer_duration_seconds,
            }
            messages.success(request, 'Quiz settings saved. Generating your quiz...')
            return redirect('quiz:generate_questions')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = QuizConfigForm(initial={'question_count': 5})

    return render(request, 'quiz/quiz_settings.html', {
        'category': category,
        'subcategory': subcategory,
        'form': form
    })


@login_required
def generate_questions(request):
    settings_data = request.session.get('quiz_settings')
    if not settings_data:
        messages.error(request, 'No quiz settings found. Configure your quiz first.')
        return redirect('quiz:category_list')
    return render(request, 'quiz/generate_questions.html', {
        'subcategory_name': settings_data.get('subcategory_name', 'Quiz')
    })


@login_required
def generate_questions_api(request):
    """Generate questions - STRICT duplicate check"""
    
    settings_data = request.session.get('quiz_settings')
    if not settings_data:
        return JsonResponse({'success': False, 'error': 'Session expired'}, status=400)

    topic = settings_data.get('subcategory_name', 'General')
    difficulty = settings_data.get('difficulty', 'medium')
    num_questions = int(settings_data.get('question_count', 5))
    
    subcategory = get_object_or_404(SubCategory, id=settings_data['subcategory_id'])
    
    # ===== STEP 1: Get ALL attempted question IDs =====
    attempted_ids = QuestionAttempt.objects.filter(
        user=request.user
    ).values_list('question_id', flat=True)
    
    # Also get hashes of attempted questions
    attempted_hashes = Question.objects.filter(
        id__in=attempted_ids
    ).values_list('question_hash', flat=True)
    
    print(f"📊 User has attempted {len(attempted_ids)} questions")
    
    # ===== STEP 2: Get available questions from database =====
    available_questions = Question.objects.filter(
        quiz__subcategory=subcategory
    ).exclude(
        id__in=attempted_ids
    ).exclude(
        question_hash__in=attempted_hashes  # Exclude similar questions by hash
    ).distinct()
    
    print(f"📚 Available unique questions: {available_questions.count()}")
    
    # ===== STEP 3: If enough unique questions, use them =====
    if available_questions.count() >= num_questions:
        # Randomly select questions
        selected_questions = list(available_questions.order_by('?')[:num_questions])
        
        # Create quiz
        total_time = num_questions * 60
        quiz = Quiz.objects.create(
            subcategory=subcategory,
            difficulty=difficulty,
            question_count=num_questions,
            timer_enabled=True,
            timer_duration_seconds=total_time,
            status='in_progress'
        )
        
        # Copy selected questions
        for order, q in enumerate(selected_questions):
            Question.objects.create(
                quiz=quiz,
                question_text=q.question_text,
                option_a=q.option_a,
                option_b=q.option_b,
                option_c=q.option_c,
                option_d=q.option_d,
                correct_index=q.correct_index,
                order=order,
                question_hash=q.question_hash  # Copy hash
            )
        
        # Session setup
        request.session['quiz_id'] = quiz.id
        request.session['quiz_start_time'] = timezone.now().isoformat()
        request.session['quiz_answers'] = {}
        request.session.modified = True
        
        return JsonResponse({
            'success': True,
            'redirect_url': reverse('quiz:quiz_take'),
            'count': num_questions,
            'source': 'database'
        })
    
    # ===== STEP 4: Generate new unique questions =====
    else:
        needed = num_questions
        print(f"⚠️ Generating {needed} new unique questions from Gemini")
        
        all_new_questions = []
        attempts = 0
        
        while len(all_new_questions) < needed and attempts < 5:
            try:
                # Generate batch
                new_batch = gen_questions(topic, difficulty, needed * 2)
                
                for q_data in new_batch:
                    if len(all_new_questions) >= needed:
                        break
                    
                    # Create hash for new question
                    import hashlib
                    q_hash = hashlib.sha256(
                        q_data['question'].lower().strip().encode()
                    ).hexdigest()[:16]
                    
                    # Check if this question already exists (anywhere)
                    similar_exists = Question.objects.filter(
                        question_hash=q_hash
                    ).exists()
                    
                    # Check if it's similar to attempted ones
                    hash_attempted = q_hash in attempted_hashes
                    
                    if not similar_exists and not hash_attempted:
                        all_new_questions.append(q_data)
                        
            except Exception as e:
                print(f"Error generating: {e}")
            
            attempts += 1
        
        if len(all_new_questions) < needed:
            return JsonResponse({
                'success': False,
                'error': f'Only {len(all_new_questions)} unique questions available'
            })
        
        # Create quiz
        total_time = needed * 60
        quiz = Quiz.objects.create(
            subcategory=subcategory,
            difficulty=difficulty,
            question_count=needed,
            timer_enabled=True,
            timer_duration_seconds=total_time,
            status='in_progress'
        )
        
        # Save new questions
        for order, q_data in enumerate(all_new_questions[:needed]):
            q_hash = hashlib.sha256(
                q_data['question'].lower().strip().encode()
            ).hexdigest()[:16]
            
            Question.objects.create(
                quiz=quiz,
                question_text=q_data['question'],
                option_a=q_data['options'][0],
                option_b=q_data['options'][1],
                option_c=q_data['options'][2],
                option_d=q_data['options'][3],
                correct_index=q_data['correct_index'],
                order=order,
                question_hash=q_hash
            )
        
        request.session['quiz_id'] = quiz.id
        request.session['quiz_start_time'] = timezone.now().isoformat()
        request.session['quiz_answers'] = {}
        request.session.modified = True
        
        return JsonResponse({
            'success': True,
            'redirect_url': reverse('quiz:quiz_take'),
            'count': needed,
            'source': 'gemini'
        })
    
@login_required
def quiz_take(request):
    """Take quiz with stable submission IDs"""
    
    quiz_id = request.session.get('quiz_id')
    if not quiz_id:
        messages.error(request, 'No quiz found.')
        return redirect('quiz:category_list')
    
    quiz = get_object_or_404(Quiz, id=quiz_id)
    quiz.last_accessed = timezone.now()
    quiz.save()
    
    questions = list(quiz.questions.all().order_by('order'))
    
    if not questions:
        messages.error(request, 'No questions in quiz.')
        return redirect('quiz:category_list')
    
    # ===== FIXED SUBMISSION IDs - Generate once, never change =====
    submission_ids = request.session.get('submission_ids', {})
    
    # First time - generate IDs for all questions
    if not submission_ids:
        for q in questions:
            qid = str(q.id)
            submission_ids[qid] = str(uuid.uuid4())[:8]  # 8 character ID
        request.session['submission_ids'] = submission_ids
        request.session.modified = True
        print(f"Generated {len(submission_ids)} submission IDs")  # Debug
    
    # Calculate time
    total_time = len(questions) * 60
    start_time_str = request.session.get('quiz_start_time')
    
    if start_time_str:
        try:
            start_time = datetime.fromisoformat(start_time_str)
            elapsed = (timezone.now() - start_time).seconds
            time_left = max(0, total_time - elapsed)
        except:
            time_left = total_time
            request.session['quiz_start_time'] = timezone.now().isoformat()
    else:
        time_left = total_time
        request.session['quiz_start_time'] = timezone.now().isoformat()
    
    # Check if time is up
    if time_left <= 0:
        return redirect('quiz:quiz_submit')
    
    # Get current question
    current_index = int(request.GET.get('q', 0))
    current_index = max(0, min(current_index, len(questions) - 1))
    current_q = questions[current_index]
    
    # Get saved answers
    answers = request.session.get('quiz_answers', {})
    answer_data = answers.get(str(current_q.id), {})
    selected_option = answer_data.get('selected') if isinstance(answer_data, dict) else None
    
    # Handle POST
    if request.method == 'POST':
        question_id = request.POST.get('question_id')
        selected = request.POST.get('selected_option')
        time_spent = request.POST.get('time_spent', 0)
        action = request.POST.get('action', 'next')
        
        if selected and selected != '' and question_id:
            try:
                answers = request.session.get('quiz_answers', {})
                # ✅ Save answer without submission ID (ID already in session)
                answers[question_id] = {
                    'selected': int(selected),
                    'time_spent': int(time_spent)
                }
                request.session['quiz_answers'] = answers
                request.session.modified = True
            except (ValueError, TypeError):
                pass
        
        # Navigation
        if action == 'submit':
            return redirect('quiz:quiz_submit')
        elif action == 'next':
            current_index = min(current_index + 1, len(questions) - 1)
        elif action == 'prev':
            current_index = max(0, current_index - 1)
        
        return redirect(f'{request.path}?q={current_index}')
    
    # Get answered count
    answered_count = len(answers)
    
    # Get submission ID for current question
    current_submission_id = submission_ids.get(str(current_q.id), '')
    
    context = {
        'category': quiz.subcategory.category,
        'subcategory': quiz.subcategory,
        'questions': questions,
        'answered_count': answered_count,
        'current_index': current_index,
        'current_question': current_q,
        'options': [current_q.option_a, current_q.option_b, current_q.option_c, current_q.option_d],
        'selected_option': selected_option,
        'total': len(questions),
        'time_left': time_left,
        'total_time': total_time,
        'current_submission_id': current_submission_id,  # ✅ For display
        'all_submission_ids': submission_ids,  # ✅ Pass all IDs to template
    }
    
    return render(request, 'quiz/quiz_take.html', context)

@login_required
def quiz_submit(request):
    """Submit quiz and mark ALL questions as attempted"""
    
    quiz_id = request.session.get('quiz_id')
    if not quiz_id:
        messages.error(request, 'No quiz found.')
        return redirect('quiz:category_list')
    
    quiz = get_object_or_404(Quiz, id=quiz_id)
    quiz.status = 'completed'
    quiz.save()
    
    questions = quiz.questions.all().order_by('order')
    answers = request.session.get('quiz_answers', {})
    submission_ids = request.session.get('submission_ids', {})
    
    correct_count = 0
    total_time = 0
    user_answers = []
    
    for q in questions:
        qid = str(q.id)
        ans = answers.get(qid, {})
        selected = ans.get('selected')
        time_spent = ans.get('time_spent', 0)
        
        total_time += time_spent
        is_correct = (selected is not None and selected == q.correct_index)
        
        if is_correct:
            correct_count += 1
        
        user_answers.append({
            'question': q,
            'selected': selected,
            'is_correct': is_correct,
            'time_spent': time_spent,
            'submission_id': submission_ids.get(qid, str(uuid.uuid4())[:8])
        })
    
    total = questions.count()
    score = (correct_count / total) * 100 if total else 0
    
    # Create QuizResult
    result = QuizResult.objects.create(
        user=request.user,
        quiz=quiz,
        total_questions=total,
        correct_answers=correct_count,
        score_percent=score,
        is_pass=score >= 50,
        total_time_taken=total_time,
        quiz_topic=quiz.subcategory.name,
        difficulty=quiz.difficulty,
    )
    
    # ===== CRITICAL: Save to QuestionAttempt for EVERY question =====
    attempt_count = 0
    skipped_count = 0
    
    for item in user_answers:
        q = item['question']
        
        # Save UserAnswer
        UserAnswer.objects.create(
            quiz_result=result,
            question=q,
            selected_index=item['selected'],
            correct_index=q.correct_index,
            is_correct=item['is_correct'],
            time_taken=item['time_spent']
        )
        
        # ===== MARK QUESTION AS ATTEMPTED =====
        try:
            attempt, created = QuestionAttempt.objects.get_or_create(
                user=request.user,
                question=q,
                defaults={
                    'quiz_result': result,
                    'submission_id': item['submission_id']
                }
            )
            if created:
                attempt_count += 1
                print(f"✅ Marked Q{q.id} as attempted")
            else:
                skipped_count += 1
                print(f"⚠️ Q{q.id} already attempted")
                
        except Exception as e:
            print(f"❌ Error marking Q{q.id}: {e}")
    
    print(f"📊 Attempts created: {attempt_count}, Skipped: {skipped_count}")
    
    # Update profile stats
    try:
        request.user.profile.update_stats()
    except:
        pass
    
    # Clear session
    for key in ['quiz_id', 'quiz_answers', 'quiz_start_time', 'submission_ids']:
        if key in request.session:
            del request.session[key]
    
    messages.success(request, f'Quiz submitted! Score: {score:.1f}%')
    return redirect('quiz:quiz_results', result_id=result.id)

@login_required
def quiz_results(request, result_id):
    quiz_result = get_object_or_404(QuizResult, id=result_id, user=request.user)
    answers = quiz_result.answers.all().select_related('question').order_by('question__order')

    results = []
    for ans in answers:
        q = ans.question
        options = [q.option_a, q.option_b, q.option_c, q.option_d]
        results.append({
            'question': q.question_text,
            'options': options,
            'correct_index': q.correct_index,
            'selected': ans.selected_index,
            'is_correct': ans.is_correct,
            'explanation': ans.ai_explanation,
        })

    context = {
        'category': quiz_result.quiz.subcategory.category,
        'subcategory': quiz_result.quiz.subcategory,
        'total': quiz_result.total_questions,
        'correct': quiz_result.correct_answers,
        'score_percent': round(quiz_result.score_percent),
        'is_pass': quiz_result.is_pass,
        'results': results,
        'quiz_result': quiz_result,
        'result_id': quiz_result.id,
        
    }
    return render(request, 'quiz/quiz_results.html', context)

@login_required
def quiz_start(request):
    settings_data = request.session.get('quiz_settings')
    if not settings_data:
        messages.error(request, 'No quiz settings found.')
        return redirect('quiz:category_list')
    if request.session.get('quiz_questions'):
        return redirect('quiz:quiz_take')
    return redirect('quiz:generate_questions')

@login_required
def incomplete_quizzes(request):
    """Show all incomplete quizzes for the user"""
    # Find quizzes that user has started but not completed
    cutoff = timezone.now() - timedelta(days=7)  # Show last 7 days
    
    incomplete = Quiz.objects.filter(
        created_at__gte=cutoff,
        status='in_progress'
    ).exclude(
        quizresult__user=request.user
    ).select_related('subcategory', 'subcategory__category')
    
    # For each quiz, count how many answers are saved
    from .models import UserAnswer
    for quiz in incomplete:
        # This is a simplified approach - in reality you'd need a QuizResult placeholder
        quiz.answered_count = UserAnswer.objects.filter(
            quiz_result__quiz=quiz,
            quiz_result__user=request.user
        ).count()
    
    context = {
        'incomplete_quizzes': incomplete
    }
    return render(request, 'quiz/incomplete_quizzes.html', context)

@login_required
def resume_quiz(request, quiz_id):
    """Resume an incomplete quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id, status='in_progress')
    
    # Store in session
    request.session['quiz_id'] = quiz.id
    request.session.modified = True
    
    messages.success(request, f'Resuming quiz: {quiz.subcategory.name}')
    return redirect('quiz:quiz_take')

@login_required
def abandon_quiz(request, quiz_id):
    """Mark a quiz as abandoned"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    quiz.status = 'abandoned'
    quiz.save(update_fields=['status'])
    
    # Clear from session if it's the current quiz
    if request.session.get('quiz_id') == quiz.id:
        del request.session['quiz_id']
    
    messages.success(request, 'Quiz abandoned successfully')
    return redirect('quiz:incomplete_quizzes')

@login_required
def quiz_history(request):
    """Display all completed quizzes with filtering and sorting"""
    quizzes = QuizResult.objects.filter(user=request.user).select_related(
        'quiz', 'quiz__subcategory', 'quiz__subcategory__category'
    )
    
    # Filtering
    category = request.GET.get('category')
    if category and category.isdigit(): 
        quizzes = quizzes.filter(quiz__subcategory__category_id=int(category))
    
    subcategory = request.GET.get('subcategory')
    # ✅ STRICT CHECK - sirf tab filter karo jab value digit ho
    if subcategory and subcategory.isdigit():
        quizzes = quizzes.filter(quiz__subcategory_id=int(subcategory))
    # Agar string hai to filter ignore karo
    elif subcategory:
        print(f"⚠️ Ignoring invalid subcategory filter: {subcategory}")


    difficulty = request.GET.get('difficulty')
    if difficulty:
        quizzes = quizzes.filter(quiz__difficulty=difficulty)
    
    date_from = request.GET.get('date_from')
    if date_from:
        quizzes = quizzes.filter(created_at__gte=date_from)
    
    date_to = request.GET.get('date_to')
    if date_to:
        quizzes = quizzes.filter(created_at__lte=date_to)
    
    search = request.GET.get('search')
    if search:
        quizzes = quizzes.filter(
            Q(quiz__subcategory__name__icontains=search) |
            Q(quiz__subcategory__category__name__icontains=search)
        )
    
    # Sorting
    sort_by = request.GET.get('sort', '-created_at')
    valid_sort_fields = ['created_at', '-created_at', 'score_percent', '-score_percent', 
                        'quiz__subcategory__name', '-quiz__subcategory__name']
    if sort_by in valid_sort_fields:
        quizzes = quizzes.order_by(sort_by)
    
    # Pagination
    paginator = Paginator(quizzes, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    from django.db.models import Count

    # SIMPLE AND SAFE APPROACH
    category_ids = QuizResult.objects.filter(
    user=request.user
    ).values_list(
    'quiz__subcategory__category_id', flat=True
    ).distinct()

    categories = Category.objects.filter(id__in=category_ids)

    subcategory_ids = QuizResult.objects.filter(
    user=request.user
    ).values_list(
    'quiz__subcategory_id', flat=True
    ).distinct()

    subcategories = SubCategory.objects.filter(id__in=subcategory_ids)
    
    # Current filters ko safe banao
    safe_category = category if category and category.isdigit() else ''
    safe_subcategory = subcategory if subcategory and subcategory.isdigit() else ''

    context = {
        'page_obj': page_obj,
        'categories': categories,
        'subcategories': subcategories,
        'current_filters': {
            'category': safe_category,
            'subcategory': safe_subcategory,
            'difficulty': difficulty if difficulty else '',
            'date_from': date_from if date_from else '',
            'date_to': date_to if date_to else '',
            'search': search if search else '',
            'sort': sort_by,
        }
    }
    return render(request, 'quiz/quiz_history.html', context)

@login_required
def leaderboard(request):
    """Display global and category-specific leaderboards"""
    leaderboard_type = request.GET.get('type', 'global')
    category_id = request.GET.get('category')
    
    # Base queryset for users with public profiles
    users = User.objects.filter(
        profile__show_on_leaderboard=True,
        profile__total_quizzes__gt=0  # YEH CONDITION LAGAO - sirf jinke quizzes hain
    ).select_related('profile')    
    # User list initialize
    user_list = []
    
    if leaderboard_type == 'global':
        # Global ranking by average score
        for user in users:
                user_list.append({
                    'user': user,
                    'avg_score': user.profile.average_score,
                    'total_quizzes': user.profile.total_quizzes,
                    'best_score': user.profile.best_score,
                    'streak': user.profile.streak,
                })
        
        # Sort by average score
        user_list.sort(key=lambda x: x['avg_score'], reverse=True)
        user_list = user_list[:50]
        
        # Add rank
        for idx, item in enumerate(user_list, 1):
            item['rank'] = idx
            item['is_current'] = (item['user'].id == request.user.id)
    
    elif leaderboard_type == 'streak':
        # Ranking by streak
        for user in users:
            if user.profile.streak > 0:
                user_list.append({
                    'user': user,
                    'streak': user.profile.streak,
                    'avg_score': user.profile.average_score,
                    'total_quizzes': user.profile.total_quizzes,
                })
        
        user_list.sort(key=lambda x: (x['streak'], x['avg_score']), reverse=True)
        user_list = user_list[:50]
        
        for idx, item in enumerate(user_list, 1):
            item['rank'] = idx
            item['is_current'] = (item['user'].id == request.user.id)
    
    elif leaderboard_type == 'category' and category_id:
        # Category-specific ranking
        for user in users:
            # Get results for this category
            results = QuizResult.objects.filter(
                user=user,
                quiz__subcategory__category_id=category_id
            )
            count = results.count()
            if count > 0:
                avg = results.aggregate(Avg('score_percent'))['score_percent__avg'] or 0
                best = results.aggregate(Max('score_percent'))['score_percent__max'] or 0
                user_list.append({
                    'user': user,
                    'avg_score': avg,
                    'total_quizzes': count,
                    'best_score': best,
                })
        
        user_list.sort(key=lambda x: x['avg_score'], reverse=True)
        user_list = user_list[:50]
        
        for idx, item in enumerate(user_list, 1):
            item['rank'] = idx
            item['is_current'] = (item['user'].id == request.user.id)
    
    # Get categories for filter dropdown
    category_ids = QuizResult.objects.values_list(
        'quiz__subcategory__category_id', flat=True
    ).distinct()
    categories = Category.objects.filter(id__in=category_ids)
    
    # Get current user's rank
    current_user_rank = None
    for item in user_list:
        if item.get('is_current'):
            current_user_rank = item['rank']
            break
    
    context = {
        'user_list': user_list,
        'leaderboard_type': leaderboard_type,
        'categories': categories,
        'selected_category': category_id,
        'current_user_rank': current_user_rank,
    }
    return render(request, 'quiz/leaderboard.html', context)

@login_required
def toggle_leaderboard_privacy(request):
    """Toggle user's visibility on leaderboard"""
    if request.method == 'POST':
        profile = request.user.profile
        profile.show_on_leaderboard = not profile.show_on_leaderboard
        profile.save()
        return JsonResponse({
            'success': True,
            'visible': profile.show_on_leaderboard
        })
    return JsonResponse({'success': False}, status=400)

from django.db.models import Avg, Min, Max, Count
from django.utils import timezone
from datetime import timedelta
import json

@login_required
def retake_quiz(request, result_id):
    """Retake a quiz with same topic and settings"""
    original_result = get_object_or_404(QuizResult, id=result_id, user=request.user)
    
    # Get original quiz settings
    subcategory = original_result.quiz.subcategory
    difficulty = original_result.quiz.difficulty
    question_count = original_result.quiz.question_count
    timer_enabled = original_result.quiz.timer_enabled
    timer_duration_seconds = original_result.quiz.timer_duration_seconds
    
    # Store in session for new quiz generation
    request.session['quiz_settings'] = {
        'category_id': subcategory.category.id,
        'subcategory_id': subcategory.id,
        'subcategory_name': subcategory.name,
        'difficulty': difficulty,
        'question_count': question_count,
        'timer_enabled': timer_enabled,
        'timer_duration_seconds': timer_duration_seconds,
        'is_retake': True,
        'original_result_id': result_id,
    }
    
    messages.success(request, f'Starting retake of {subcategory.name} quiz!')
    return redirect('quiz:generate_questions')


@login_required
def quiz_comparison(request, topic=None):
    """Compare performance across multiple attempts of same quiz topic"""
    from django.db.models import Avg, Max
    from .models import QuizResult
    import json
    
    # Agar user ke paas koi result nahi
    if not QuizResult.objects.filter(user=request.user).exists():
        return render(request, 'quiz/comparison.html', {'error': 'No quizzes taken yet'})
    
    # AGAR TOPIC DIYA HAI
    if topic:
        # Case-insensitive filter
        results = QuizResult.objects.filter(
            user=request.user,
            quiz_topic__iexact=topic
        ).order_by('attempt_number')
        
        if not results.exists():
            return redirect('/quiz/comparison/')
        
        # Metrics calculate karo
        first = results.first()
        last = results.last()
        
        # Best score calculate karo
        best = results.aggregate(Max('score_percent'))['score_percent__max'] or 0
        
        # Average score calculate karo
        avg = results.aggregate(Avg('score_percent'))['score_percent__avg'] or 0
        
        metrics = {
            'total_attempts': results.count(),
            'first_score': round(first.score_percent) if first else 0,
            'last_score': round(last.score_percent) if last else 0,
            'improvement': round(last.score_percent - first.score_percent, 1) if first and last else 0,
            'best_score': round(best),
            'avg_score': round(avg),
        }
        
        # Time data
        has_timer = any(r.total_time_taken > 0 for r in results)
        time_data = [r.total_time_taken for r in results] if has_timer else []
        
        context = {
            'results': results,
            'topic': topic,
            'metrics': metrics,
            'attempt_numbers': json.dumps([r.attempt_number for r in results]),
            'score_data': json.dumps([round(r.score_percent) for r in results]),
            'time_data': json.dumps(time_data) if has_timer else '[]',
            'has_timer': has_timer,
        }
        
        # Debug - print karo terminal mein
        print("\n" + "="*50)
        print(f"Topic: {topic}")
        print(f"Total attempts: {metrics['total_attempts']}")
        print(f"First score: {metrics['first_score']}%")
        print(f"Last score: {metrics['last_score']}%")
        print(f"Best score: {metrics['best_score']}%")
        print(f"Average score: {metrics['avg_score']}%")
        print("="*50 + "\n")
        
        return render(request, 'quiz/comparison.html', context)
    
    # TOPIC LIST
    all_results = QuizResult.objects.filter(user=request.user)
    
    # Group by topic (case-insensitive)
    topic_dict = {}
    for result in all_results:
        normalized = result.quiz_topic.lower().strip()
        if normalized not in topic_dict:
            topic_dict[normalized] = {
                'name': result.quiz_topic,  # Original name for display
                'attempts': 0,
                'best': 0
            }
        topic_dict[normalized]['attempts'] += 1
        if result.score_percent > topic_dict[normalized]['best']:
            topic_dict[normalized]['best'] = result.score_percent
    
    # Convert to list
    topic_data = list(topic_dict.values())
    
    # Sort alphabetically
    topic_data.sort(key=lambda x: x['name'].lower())
    
    context = {
        'topics': topic_data,
        'show_topics': True
    }
    return render(request, 'quiz/comparison.html', context)


@login_required
def attempt_details(request, result_id):
    """View details of a specific attempt"""
    result = get_object_or_404(QuizResult, id=result_id, user=request.user)
    answers = result.answers.all().select_related('question').order_by('question__order')
    
    results_data = []
    for ans in answers:
        q = ans.question
        options = [q.option_a, q.option_b, q.option_c, q.option_d]
        results_data.append({
            'question': q.question_text,
            'options': options,
            'correct_index': q.correct_index,
            'selected': ans.selected_index,
            'is_correct': ans.is_correct,
            'explanation': ans.ai_explanation,
        })
    
    context = {
        'result': result,
        'results': results_data,
        'category': result.quiz.subcategory.category,
        'subcategory': result.quiz.subcategory,
    }
    return render(request, 'quiz/attempt_details.html', context)

# quiz/utils.py ya views.py ke end mein add karo

def get_available_questions_count(user, subcategory):
    """Get count of questions user hasn't attempted"""
    attempted = QuestionAttempt.objects.filter(
        user=user
    ).values_list('question_id', flat=True)
    
    available = Question.objects.filter(
        quiz__subcategory=subcategory
    ).exclude(
        id__in=attempted
    ).count()
    
    return available

def has_user_attempted_question(user, question):
    """Check if user has attempted specific question"""
    return QuestionAttempt.objects.filter(
        user=user,
        question=question
    ).exists()