from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    image = models.ImageField(default='profile_pics/default.jpg', upload_to='profile_pics')
    bio = models.TextField(blank=True)
    preferences = models.TextField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('user', 'User'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')
    
    # Leaderboard fields
    total_score = models.FloatField(default=0)
    total_quizzes = models.IntegerField(default=0)
    average_score = models.FloatField(default=0)
    best_score = models.FloatField(default=0)
    show_on_leaderboard = models.BooleanField(default=True)
    streak = models.IntegerField(default=0)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    def update_stats(self):
        """Update user statistics based on quiz results"""
        from quiz.models import QuizResult
        from django.db.models import Avg, Max
        
        results = QuizResult.objects.filter(user=self.user)
        self.total_quizzes = results.count()
        
        if self.total_quizzes > 0:
            # Average score
            avg_result = results.aggregate(Avg('score_percent'))
            self.average_score = avg_result['score_percent__avg'] or 0
            
            # Best score
            best_result = results.aggregate(Max('score_percent'))
            self.best_score = best_result['score_percent__max'] or 0
            
            # Total score (sum of all percentages)
            total = 0
            for result in results:
                total += result.score_percent
            self.total_score = total
            
            # Calculate streak (consecutive passes)
            streak = 0
            for result in results.order_by('-created_at'):
                if result.is_pass:
                    streak += 1
                else:
                    break
            self.streak = streak
        
        self.save()
        return True

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    """Create profile when new user is created"""
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    """Save profile when user is saved"""
    instance.profile.save()