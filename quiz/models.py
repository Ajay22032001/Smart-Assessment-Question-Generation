from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='subcategories'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ('category', 'name')
        ordering = ['name']

    def __str__(self):
        return f'{self.category.name} - {self.name}'


class Quiz(models.Model):
    subcategory = models.ForeignKey(SubCategory, on_delete=models.CASCADE, related_name='quizzes')
    difficulty = models.CharField(max_length=20, default='medium')
    question_count = models.PositiveIntegerField(default=10)
    timer_enabled = models.BooleanField(default=False)
    timer_duration_seconds = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    status = models.CharField(max_length=20, choices=[('in_progress', 'In Progress'), ('completed', 'Completed'), ('abandoned', 'Abandoned')], default='in_progress')
    last_accessed = models.DateTimeField(auto_now=True)
    current_question_index = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return f"Quiz - {self.subcategory.name} ({self.created_at.date()})"
    
# quiz/models.py - Add hash field to detect duplicate questions

class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_index = models.PositiveSmallIntegerField(default=0)
    order = models.PositiveIntegerField(default=0)
    
    # ✅ Add hash to detect duplicate questions
    question_hash = models.CharField(max_length=64, blank=True, null=True)
    
    # Track which users have seen this question
    attempted_users = models.ManyToManyField(
        User, 
        through='QuestionAttempt',
        related_name='attempted_questions',
        blank=True
    )
    
    class Meta:
        ordering = ['order']
    
    def save(self, *args, **kwargs):
        # Generate hash from question text (to detect duplicates)
        import hashlib
        if not self.question_hash:
            text = self.question_text.lower().strip()
            self.question_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.question_text[:50] + '...'
    

class QuestionAttempt(models.Model):
    """Track question attempts per user - NEW MODEL"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='question_attempts')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='attempts')
    quiz_result = models.ForeignKey('QuizResult', on_delete=models.CASCADE, null=True, blank=True, related_name='question_attempts')
    attempted_at = models.DateTimeField(auto_now_add=True)
    submission_id = models.CharField(max_length=100, unique=True)  # Unique ID for each attempt
    
    class Meta:
        unique_together = ('user', 'question')  # User can't attempt same question twice
        ordering = ['-attempted_at']
        
    def __str__(self):
        return f"{self.user.username} - Q{self.question.id} - {self.submission_id[:8]}"

class QuizResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    
    total_questions = models.IntegerField()
    correct_answers = models.IntegerField()
    score_percent = models.FloatField()
    is_pass = models.BooleanField(default=False)
    
    total_time_taken = models.IntegerField(default=0)  # seconds

    # Add these new fields for retake tracking
    attempt_number = models.IntegerField(default=1)  # Track attempt number
    quiz_topic = models.CharField(max_length=200, blank=True)  # Store topic name for grouping
    difficulty = models.CharField(max_length=20, default='medium')  # Store difficulty
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.score_percent}%"
    
    class Meta:
        ordering = ['-created_at']


class UserAnswer(models.Model):
    quiz_result = models.ForeignKey(QuizResult, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)

    selected_index = models.IntegerField(null=True, blank=True)
    correct_index = models.IntegerField()

    is_correct = models.BooleanField(default=False)

    time_taken = models.IntegerField(default=0)  # seconds per question

    ai_explanation = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Q{self.question.id} - {self.selected_index}"

# Signal to update profile when quiz result is saved
@receiver(post_save, sender=QuizResult)
def update_profile_on_quiz_complete(sender, instance, created, **kwargs):
    """Update user profile statistics when a quiz result is saved"""
    if created:  # Sirf naye results ke liye
        instance.user.profile.update_stats()