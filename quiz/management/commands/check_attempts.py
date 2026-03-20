from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from quiz.models import QuestionAttempt, QuizResult, Question
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Check user question attempts'
    
    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Username to check')
        parser.add_argument('--topic', type=str, help='Topic to check')
        parser.add_argument('--question', type=int, help='Question ID to check')
    
    def handle(self, *args, **options):
        username = options.get('username')
        
        if options.get('question'):
            self.check_question(options['question'])
        elif username:
            self.check_user(username, options.get('topic'))
        else:
            self.check_all()
    
    def check_user(self, username, topic=None):
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User {username} not found"))
            return
        
        self.stdout.write(self.style.SUCCESS(f"\n=== CHECKING USER: {username} ==="))
        
        # Total attempts
        attempts = QuestionAttempt.objects.filter(user=user)
        self.stdout.write(f"Total attempts: {attempts.count()}")
        
        # Unique questions
        unique = attempts.values('question').distinct().count()
        self.stdout.write(f"Unique questions: {unique}")
        
        # Topic specific
        if topic:
            topic_attempts = attempts.filter(
                question__quiz__subcategory__name__icontains=topic
            )
            self.stdout.write(f"\nTopic '{topic}': {topic_attempts.count()} attempts")
            
            total_in_topic = Question.objects.filter(
                quiz__subcategory__name__icontains=topic
            ).count()
            self.stdout.write(f"Total in topic: {total_in_topic}")
            self.stdout.write(f"New available: {total_in_topic - topic_attempts.count()}")
        
        # Recent
        week_ago = timezone.now() - timedelta(days=7)
        recent = attempts.filter(attempted_at__gte=week_ago)
        self.stdout.write(f"\nLast 7 days: {recent.count()} attempts")
        
    def check_question(self, question_id):
        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Question {question_id} not found"))
            return
        
        self.stdout.write(self.style.SUCCESS(f"\n=== CHECKING QUESTION: {question_id} ==="))
        self.stdout.write(f"Question: {question.question_text[:100]}...")
        
        attempts = QuestionAttempt.objects.filter(question=question)
        self.stdout.write(f"Total attempts: {attempts.count()}")
        
        users = attempts.values('user').distinct().count()
        self.stdout.write(f"Unique users: {users}")
        
        if attempts.exists():
            self.stdout.write("\nRecent attempts:")
            for a in attempts.order_by('-attempted_at')[:5]:
                self.stdout.write(f"  {a.user.username} - {a.attempted_at.date()} - {a.submission_id[:8]}")
    
    def check_all(self):
        self.stdout.write(self.style.SUCCESS("\n=== SYSTEM WIDE STATS ==="))
        
        total_attempts = QuestionAttempt.objects.count()
        self.stdout.write(f"Total attempts: {total_attempts}")
        
        total_users = QuestionAttempt.objects.values('user').distinct().count()
        self.stdout.write(f"Total users: {total_users}")
        
        total_questions = QuestionAttempt.objects.values('question').distinct().count()
        self.stdout.write(f"Total questions attempted: {total_questions}")
        
        # Users with most attempts
        self.stdout.write("\nTop users:")
        top_users = QuestionAttempt.objects.values(
            'user__username'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        for u in top_users:
            self.stdout.write(f"  {u['user__username']}: {u['count']} attempts")