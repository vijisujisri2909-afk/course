from django.db import models
from django.contrib.auth.models import User


class CourseTopic(models.Model):
    title = models.CharField(max_length=255)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_topics')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Quiz(models.Model):
    topic = models.ForeignKey(CourseTopic, on_delete=models.CASCADE, related_name='quizzes')
    title = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()

    def __str__(self):
        return self.question_text[:80]


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.TextField()
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.answer_text[:80]


class GeneratedContent(models.Model):
    topic = models.ForeignKey(CourseTopic, on_delete=models.CASCADE, related_name='generated_content')
    quiz = models.ForeignKey(
        Quiz, on_delete=models.SET_NULL, null=True, blank=True, related_name='generated_contents'
    )
    notes = models.TextField()
    key_points = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Generated content for {self.topic.title}'


class Summary(models.Model):
    topic = models.ForeignKey(CourseTopic, on_delete=models.CASCADE, related_name='summaries')
    summary_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Summary for {self.topic.title}'
