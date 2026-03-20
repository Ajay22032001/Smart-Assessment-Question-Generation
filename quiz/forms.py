
from django import forms


class QuizConfigForm(forms.Form):

    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    QUESTION_COUNT_CHOICES = [
        (5, '5 Questions'),
        (10, '10 Questions'),
        (15, '15 Questions'),
    ]

    difficulty = forms.ChoiceField(
        choices=DIFFICULTY_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='Difficulty Level',
        required=True,
        initial='easy',
    )
    question_count = forms.ChoiceField(
        choices=QUESTION_COUNT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Number of Questions',
        required=True,
    )
    timer_enabled = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Enable Timer',
    )

    def clean_question_count(self):
        """Validate question count is within allowed range."""
        value = self.cleaned_data.get('question_count')
        if value:
            try:
                count = int(value)
                if count not in [5, 10, 15]:
                    raise forms.ValidationError('Please select 5, 10, or 15 questions.')
                return value
            except (ValueError, TypeError):
                raise forms.ValidationError('Invalid question count.')
        return value
