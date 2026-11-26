import asyncio
import io
import json
import logging
import os

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from xml.sax.saxutils import escape

from .forms import CourseTopicForm
from .models import Answer, CourseTopic, GeneratedContent, Question, Quiz, Summary


logger = logging.getLogger(__name__)


GEMINI_ENDPOINT = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    'gemini-2.5-flash-preview-05-20:generateContent'
)


async def request_gemini_content(topic: str, api_key: str) -> dict:
    prompt = f'''Act as an expert educational content generator. Create clear, accurate,
well-structured learning material for the course topic: "{topic}".

Return only a JSON object with this exact shape:
{{
  "notes": "A thorough but accessible explanation of the topic in Markdown.",
  "keyPoints": ["Important point 1", "Important point 2"],
  "summary": "A concise summary of the topic.",
  "quiz": {{
    "title": "A quiz title",
    "description": "A short quiz description.",
    "questions": [
      {{"questionText": "A multiple-choice question?", "options": [
        {{"text": "Option A", "isCorrect": true}},
        {{"text": "Option B", "isCorrect": false}}
      ]}}
    ]
  }}
}}

Include useful definitions, examples, and practical context. Do not add any text
outside the JSON object.'''
    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'responseMimeType': 'application/json',
            'responseSchema': {
                'type': 'OBJECT',
                'properties': {
                    'notes': {'type': 'STRING'},
                    'keyPoints': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
                    'summary': {'type': 'STRING'},
                    'quiz': {
                        'type': 'OBJECT',
                        'properties': {
                            'title': {'type': 'STRING'},
                            'description': {'type': 'STRING'},
                            'questions': {
                                'type': 'ARRAY',
                                'items': {
                                    'type': 'OBJECT',
                                    'properties': {
                                        'questionText': {'type': 'STRING'},
                                        'options': {
                                            'type': 'ARRAY',
                                            'items': {
                                                'type': 'OBJECT',
                                                'properties': {
                                                    'text': {'type': 'STRING'},
                                                    'isCorrect': {'type': 'BOOLEAN'},
                                                },
                                                'required': ['text', 'isCorrect'],
                                            },
                                        },
                                    },
                                    'required': ['questionText', 'options'],
                                },
                            },
                        },
                        'required': ['title', 'description', 'questions'],
                    },
                },
                'required': ['notes', 'keyPoints', 'summary', 'quiz'],
            },
        },
    }
    response = await asyncio.to_thread(
        requests.post,
        GEMINI_ENDPOINT,
        params={'key': api_key},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    response_data = response.json()
    generated_text = response_data['candidates'][0]['content']['parts'][0]['text']
    result = json.loads(generated_text)
    if not isinstance(result.get('notes'), str) or not isinstance(result.get('keyPoints'), list):
        raise ValueError('Gemini returned an unexpected content shape.')
    if not isinstance(result.get('summary'), str) or not isinstance(result.get('quiz'), dict):
        raise ValueError('Gemini returned incomplete summary or quiz data.')
    return result


def _save_generated_data(topic, result):
    quiz_data = result['quiz']
    if not isinstance(quiz_data.get('title'), str) or not isinstance(quiz_data.get('description'), str):
        raise ValueError('Quiz title or description is invalid.')
    if not isinstance(quiz_data.get('questions'), list):
        raise ValueError('Quiz questions are invalid.')

    with transaction.atomic():
        quiz = Quiz.objects.create(
            topic=topic,
            title=quiz_data['title'],
            description=quiz_data['description'],
        )
        for question_data in quiz_data['questions']:
            if not isinstance(question_data, dict) or not isinstance(question_data.get('questionText'), str):
                raise ValueError('A quiz question is invalid.')
            question = Question.objects.create(quiz=quiz, question_text=question_data['questionText'])
            options = question_data.get('options')
            if not isinstance(options, list):
                raise ValueError('Quiz answer options are invalid.')
            for option in options:
                if not isinstance(option, dict) or not isinstance(option.get('text'), str):
                    raise ValueError('A quiz answer is invalid.')
                Answer.objects.create(
                    question=question,
                    answer_text=option['text'],
                    is_correct=bool(option.get('isCorrect', False)),
                )

        GeneratedContent.objects.create(
            topic=topic,
            quiz=quiz,
            notes=result['notes'],
            key_points=json.dumps(result['keyPoints'], ensure_ascii=False),
        )
        Summary.objects.create(topic=topic, summary_text=result['summary'])
    return quiz


@login_required
def generate_content(request):
    if request.method == 'POST':
        form = CourseTopicForm(request.POST)
        if form.is_valid():
            api_key = getattr(settings, 'GEMINI_API_KEY', '') or os.environ.get('GEMINI_API_KEY', '')
            if not api_key:
                form.add_error(None, 'Set GEMINI_API_KEY before generating content.')
            else:
                try:
                    result = asyncio.run(request_gemini_content(form.cleaned_data['title'], api_key))
                except (requests.RequestException, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    logger.exception('Gemini content generation failed')
                    form.add_error(None, f'Unable to generate content: {error}')
                else:
                    try:
                        with transaction.atomic():
                            topic = form.save(commit=False)
                            topic.teacher = request.user
                            topic.save()
                            _save_generated_data(topic, result)
                    except Exception as error:
                        logger.exception('Saving generated quiz and summary failed')
                        form.add_error(None, f'Unable to save generated content: {error}')
                    else:
                        return redirect('generator:content_detail', topic_id=topic.pk)
    else:
        form = CourseTopicForm()
    return render(request, 'generator/generate_content.html', {'form': form})


@login_required
def content_detail(request, topic_id):
    topic = get_object_or_404(CourseTopic, pk=topic_id, teacher=request.user)
    content = topic.generated_content.first()
    key_points = json.loads(content.key_points) if content else []
    summary = topic.summaries.first()
    quiz = content.quiz if content and content.quiz_id else topic.quizzes.first()
    return render(request, 'generator/content_detail.html', {
        'topic': topic,
        'content': content,
        'key_points': key_points,
        'summary': summary,
        'quiz': quiz,
    })


@login_required
def student_dashboard(request):
    topics = CourseTopic.objects.all().prefetch_related('generated_content', 'summaries')
    return render(request, 'generator/student_dashboard.html', {'topics': topics})


@login_required
def view_content(request, topic_id):
    topic = get_object_or_404(CourseTopic, pk=topic_id)
    content = topic.generated_content.select_related('quiz').first()
    key_points = json.loads(content.key_points) if content else []
    summary = topic.summaries.first()
    quiz = content.quiz if content and content.quiz_id else topic.quizzes.first()
    return render(request, 'generator/view_content.html', {
        'topic': topic,
        'content': content,
        'key_points': key_points,
        'summary': summary,
        'quiz': quiz,
    })


@login_required
def submit_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    if request.method != 'POST':
        return redirect('generator:view_content', topic_id=quiz.topic_id)

    results = []
    score = 0
    questions = quiz.questions.prefetch_related('answers').all()
    for question in questions:
        selected_id = request.POST.get(f'question_{question.pk}')
        selected_answer = next(
            (answer for answer in question.answers.all() if str(answer.pk) == selected_id),
            None,
        )
        correct_answer = next((answer for answer in question.answers.all() if answer.is_correct), None)
        is_correct = bool(selected_answer and selected_answer.is_correct)
        if is_correct:
            score += 1
        results.append({
            'question': question,
            'selected_answer': selected_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
        })
    return render(request, 'generator/quiz_results.html', {
        'quiz': quiz,
        'score': score,
        'total': len(results),
        'results': results,
    })


@login_required
def export_pdf(request, topic_id):
    topic = get_object_or_404(CourseTopic, pk=topic_id)
    content = topic.generated_content.select_related('quiz').first()
    summary = topic.summaries.first()
    quiz = content.quiz if content and content.quiz_id else topic.quizzes.first()
    key_points = json.loads(content.key_points) if content else []

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=0.7 * inch, leftMargin=0.7 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CoverTitle', parent=styles['Title'], alignment=TA_CENTER, fontSize=24, leading=30))
    styles.add(ParagraphStyle(name='CoverMeta', parent=styles['Normal'], alignment=TA_CENTER, fontSize=12, leading=18))
    styles.add(ParagraphStyle(name='Section', parent=styles['Heading2'], textColor=colors.HexColor('#1d4ed8'), spaceBefore=14))
    styles.add(ParagraphStyle(name='BodyReadable', parent=styles['BodyText'], leading=16, spaceAfter=8))

    story = [
        Spacer(1, 1.5 * inch),
        Paragraph(escape(topic.title), styles['CoverTitle']),
        Spacer(1, 0.25 * inch),
        Paragraph('AI-generated learning material', styles['CoverMeta']),
        Paragraph(f'Teacher: {escape(topic.teacher.get_full_name() or topic.teacher.username)}', styles['CoverMeta']),
        PageBreak(),
    ]
    if summary:
        story.extend([Paragraph('Summary', styles['Section']), Paragraph(escape(summary.summary_text).replace('\n', '<br/>'), styles['BodyReadable'])])
    if content:
        story.extend([Paragraph('Notes', styles['Section']), Paragraph(escape(content.notes).replace('\n', '<br/>'), styles['BodyReadable'])])
        story.append(Paragraph('Key points', styles['Section']))
        story.extend(Paragraph(f'• {escape(str(point))}', styles['BodyReadable']) for point in key_points)
    if quiz:
        story.extend([Paragraph(escape(quiz.title), styles['Section']), Paragraph(escape(quiz.description), styles['BodyReadable'])])
        for number, question in enumerate(quiz.questions.prefetch_related('answers').all(), start=1):
            story.append(Paragraph(f'{number}. {escape(question.question_text)}', styles['BodyReadable']))
            rows = [[escape(answer.answer_text), 'Correct answer' if answer.is_correct else ''] for answer in question.answers.all()]
            if rows:
                table = Table(rows, colWidths=[4.7 * inch, 1.5 * inch])
                table.setStyle(TableStyle([
                    ('GRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
                ]))
                story.extend([table, Spacer(1, 0.12 * inch)])
    document.build(story)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f'{topic.title[:80]}.pdf', content_type='application/pdf')

# Create your views here.
