from django import forms

from .models import CourseTopic


class CourseTopicForm(forms.ModelForm):
    class Meta:
        model = CourseTopic
        fields = ['title']
        labels = {'title': 'Course topic'}
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'e.g. Introduction to machine learning',
                'autocomplete': 'off',
            }),
        }
