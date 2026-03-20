"""
Management command to populate categories and subcategories (Task 5 & 6).
Uses get_or_create by name so it works regardless of existing IDs.
"""
from django.core.management.base import BaseCommand
from quiz.models import Category, SubCategory


INITIAL_DATA = {
    "Academic": [
        ("Physics", "The study of matter and energy."),
        ("Chemistry", "The study of substances and reactions."),
    ],
    "Entertainment": [
        ("Movies", "Test your knowledge of films and cinema."),
        ("Music", "Explore genres, artists, and music theory."),
    ],
    "General Knowledge": [
        ("Current Affairs", "Stay updated with recent events and news."),
        ("History", "Journey through past events and civilizations."),
    ],
}


class Command(BaseCommand):
    help = "Populate quiz categories and subcategories (Task 5/6 initial data)"

    def handle(self, *args, **options):
        created_cats = 0
        created_subcats = 0

        for cat_name, subcats in INITIAL_DATA.items():
            category, cat_created = Category.objects.get_or_create(
                name=cat_name,
                defaults={"description": f"{cat_name} quizzes.", "image": None},
            )
            if cat_created:
                created_cats += 1

            for sub_name, sub_desc in subcats:
                _, sub_created = SubCategory.objects.get_or_create(
                    category=category,
                    name=sub_name,
                    defaults={"description": sub_desc},
                )
                if sub_created:
                    created_subcats += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {created_cats} categories, {created_subcats} subcategories."
            )
        )
