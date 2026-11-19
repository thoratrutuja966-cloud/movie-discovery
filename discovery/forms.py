from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import MovieReview, ReviewReport


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class MovieReviewForm(forms.ModelForm):
    class Meta:
        model = MovieReview
        fields = ("rating", "text")
        widgets = {
            "rating": forms.Select(choices=[(value, f"{value} / 10") for value in range(10, 0, -1)]),
            "text": forms.Textarea(attrs={"rows": 4, "maxlength": 5000, "placeholder": "What did you think of the film?"}),
        }


class ReviewReportForm(forms.ModelForm):
    class Meta:
        model = ReviewReport
        fields = ("reason", "details")
        widgets = {"details": forms.TextInput(attrs={"maxlength": 500, "placeholder": "Optional details"})}
