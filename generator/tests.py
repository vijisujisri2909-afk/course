from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Answer, CourseTopic, GeneratedContent, Question, Quiz, Summary


class ModelCrudTests(TestCase):
    def test_course_content_and_quiz_models_support_crud(self):
        teacher = User.objects.create_user(username='model-teacher')
        topic = CourseTopic.objects.create(title='Original topic', teacher=teacher)
        topic.title = 'Updated topic'
        topic.save()
        quiz = Quiz.objects.create(topic=topic, title='Quiz', description='Description')
        question = Question.objects.create(quiz=quiz, question_text='Question')
        answer = Answer.objects.create(question=question, answer_text='Answer', is_correct=True)
        content = GeneratedContent.objects.create(topic=topic, quiz=quiz, notes='Notes', key_points='[]')
        summary = Summary.objects.create(topic=topic, summary_text='Summary')

        self.assertEqual(CourseTopic.objects.get(pk=topic.pk).title, 'Updated topic')
        self.assertTrue(answer.is_correct)
        self.assertEqual(content.quiz, quiz)
        self.assertEqual(summary.topic, topic)

        answer.delete()
        question.delete()
        quiz.delete()
        content.delete()
        summary.delete()
        topic.delete()
        self.assertFalse(CourseTopic.objects.filter(pk=topic.pk).exists())


class ContentGenerationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='teacher', password='test-password')
        self.client.force_login(self.user)

    def test_get_renders_topic_form(self):
        response = self.client.get(reverse('generator:generate_content'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI Course Content Generator')

    @patch('generator.views.requests.post')
    @patch('generator.views.settings.GEMINI_API_KEY', 'test-key')
    def test_post_saves_generated_content_and_redirects(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            'candidates': [{'content': {'parts': [
                {'text': '{"notes": "Test notes", "keyPoints": ["Point one"], "summary": "Test summary", "quiz": {"title": "Test quiz", "description": "Test description", "questions": [{"questionText": "Question?", "options": [{"text": "Yes", "isCorrect": true}, {"text": "No", "isCorrect": false}]}]}}'}
            ]}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        response = self.client.post(
            reverse('generator:generate_content'), {'title': 'Python basics'}
        )

        self.assertRedirects(response, reverse('generator:content_detail', args=[1]))
        topic = CourseTopic.objects.get(title='Python basics')
        self.assertEqual(topic.teacher, self.user)
        self.assertEqual(GeneratedContent.objects.get(topic=topic).notes, 'Test notes')
        self.assertEqual(Summary.objects.get(topic=topic).summary_text, 'Test summary')
        quiz = Quiz.objects.get(topic=topic)
        question = Question.objects.get(quiz=quiz)
        self.assertEqual(question.question_text, 'Question?')
        self.assertEqual(Answer.objects.filter(question=question).count(), 2)

    def test_student_can_view_topic_and_submit_quiz(self):
        topic = CourseTopic.objects.create(title='Django basics', teacher=self.user)
        quiz = Quiz.objects.create(topic=topic, title='Django quiz', description='Check your knowledge')
        question = Question.objects.create(quiz=quiz, question_text='Is Django Python-based?')
        correct = Answer.objects.create(question=question, answer_text='Yes', is_correct=True)
        Answer.objects.create(question=question, answer_text='No', is_correct=False)
        GeneratedContent.objects.create(
            topic=topic, quiz=quiz, notes='Notes', key_points='["Point"]'
        )
        Summary.objects.create(topic=topic, summary_text='Summary')

        dashboard = self.client.get(reverse('generator:student_dashboard'))
        content = self.client.get(reverse('generator:view_content', args=[topic.pk]))
        results = self.client.post(
            reverse('generator:submit_quiz', args=[quiz.pk]),
            {f'question_{question.pk}': correct.pk},
        )

        self.assertContains(dashboard, 'Django basics')
        self.assertContains(content, 'Is Django Python-based?')
        self.assertContains(results, 'Score: 1 / 1')

    def test_export_pdf_returns_downloadable_pdf(self):
        topic = CourseTopic.objects.create(title='PDF topic', teacher=self.user)
        quiz = Quiz.objects.create(topic=topic, title='PDF quiz', description='Quiz')
        question = Question.objects.create(quiz=quiz, question_text='Question?')
        Answer.objects.create(question=question, answer_text='Correct', is_correct=True)
        GeneratedContent.objects.create(topic=topic, quiz=quiz, notes='PDF notes', key_points='["Point"]')
        Summary.objects.create(topic=topic, summary_text='PDF summary')

        response = self.client.get(reverse('generator:export_pdf', args=[topic.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))


class FixtureDataTests(TestCase):
    fixtures = ['test_data.json']

    def test_fixture_loads_related_learning_data(self):
        topic = CourseTopic.objects.get(pk=100)
        self.assertEqual(topic.quizzes.count(), 1)
        self.assertEqual(topic.summaries.count(), 1)
        self.assertEqual(topic.quizzes.first().questions.count(), 1)

# Create your tests here.
