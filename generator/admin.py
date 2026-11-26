from django.contrib import admin
from .models import Answer, CourseTopic, GeneratedContent, Question, Quiz, Summary


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 2


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 1
    show_change_link = True


@admin.register(CourseTopic)
class CourseTopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'teacher', 'created_at')
    list_filter = ('teacher', 'created_at')
    search_fields = ('title', 'teacher__username', 'teacher__email')
    date_hierarchy = 'created_at'


@admin.register(GeneratedContent)
class GeneratedContentAdmin(admin.ModelAdmin):
    list_display = ('topic', 'quiz', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('topic__title', 'notes', 'key_points')
    readonly_fields = ('created_at',)


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'topic', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('title', 'description', 'topic__title')
    inlines = (QuestionInline,)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'quiz')
    search_fields = ('question_text', 'quiz__title')
    inlines = (AnswerInline,)


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('answer_text', 'question', 'is_correct')
    list_filter = ('is_correct',)
    search_fields = ('answer_text', 'question__question_text')


@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ('topic', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('topic__title', 'summary_text')
