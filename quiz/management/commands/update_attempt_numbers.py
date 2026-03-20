from django.core.management.base import BaseCommand
from quiz.models import QuizResult
from django.db.models import Count

class Command(BaseCommand):
    help = 'Update attempt numbers for existing quiz results'

    def handle(self, *args, **options):
        self.stdout.write("Updating attempt numbers...")
        
        # Group results by user and topic
        users = QuizResult.objects.values_list('user', flat=True).distinct()
        
        for user_id in users:
            topics = QuizResult.objects.filter(
                user_id=user_id
            ).values_list('quiz_topic', flat=True).distinct()
            
            for topic in topics:
                if topic:
                    results = QuizResult.objects.filter(
                        user_id=user_id,
                        quiz_topic=topic
                    ).order_by('created_at')
                    
                    for idx, result in enumerate(results, 1):
                        result.attempt_number = idx
                        result.save(update_fields=['attempt_number'])
                        self.stdout.write(f"  Updated {result.user.username} - {topic}: attempt {idx}")
        
        self.stdout.write(self.style.SUCCESS("Successfully updated attempt numbers"))