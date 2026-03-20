from django.core.management.base import BaseCommand
from users.models import Profile

class Command(BaseCommand):
    help = 'Update all user profiles with latest quiz statistics'

    def handle(self, *args, **options):
        self.stdout.write("Updating profiles...")
        
        profiles = Profile.objects.all()
        updated_count = 0
        
        for profile in profiles:
            old_quizzes = profile.total_quizzes
            profile.update_stats()
            new_quizzes = profile.total_quizzes
            
            if new_quizzes > 0:
                updated_count += 1
                self.stdout.write(f"  Updated {profile.user.username}: {old_quizzes} → {new_quizzes} quizzes")
        
        self.stdout.write(self.style.SUCCESS(f"Successfully updated {updated_count} profiles"))