import os
import tempfile
from datetime import timedelta
from unittest import mock

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from plans.models import Checkpoint, PlanDocument
from projects.models import Project
from projects.services import create_project, current_project, is_leader
from projects.testing import add_to, api_as, make_project, make_user

URL = '/api/files/plan'
PDF = b'%PDF-1.4\n% fake pdf\n'


class PlanFileApiTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        override = override_settings(MEDIA_ROOT=tmp.name)  # 테스트가 만든 파일은 임시 폴더에만
        override.enable()
        self.addCleanup(override.disable)
        self.media = tmp.name
        self.project, self.leader = make_project()
        self.client = api_as(self.leader)

    def post(self, name='캠퍼스앱_기획안_v3.pdf', content=PDF, client=None, **fields):
        data = {'file': SimpleUploadedFile(name, content), **fields} if name else fields
        return (client or self.client).post(URL, data, format='multipart')

    def stored_files(self):
        return [f for _, _, files in os.walk(self.media) for f in files]

    # ───── 올리기 ─────

    def test_answers_with_the_front_end_plan_file_shape(self):
        res = self.post()
        self.assertEqual(res.status_code, 201, res.json())
        doc = PlanDocument.objects.get()
        self.assertEqual(res.json(), {'id': str(doc.pk), 'name': '캠퍼스앱_기획안_v3.pdf', 'size': len(PDF), 'type': 'application/pdf', 'pages': None})

    def test_document_row_and_stored_file(self):
        self.post()
        doc = PlanDocument.objects.get()
        self.assertEqual((doc.project, doc.uploaded_by, doc.source_type, doc.is_current), (self.project, self.leader, 'file', True))
        self.assertEqual((doc.file_name, doc.file_size, doc.mime_type, doc.page_count), ('캠퍼스앱_기획안_v3.pdf', len(PDF), 'application/pdf', None))
        self.assertIsNone(doc.text_content)
        # 저장 이름은 무작위 — 사용자가 정한 이름은 경로에 안 써요
        self.assertTrue(doc.storage_url.startswith(f'plans/{self.project.pk}/') and doc.storage_url.endswith('.pdf'))
        self.assertNotIn('캠퍼스앱', doc.storage_url)
        with default_storage.open(doc.storage_url) as f:
            self.assertEqual(f.read(), PDF)

    def test_path_pieces_in_the_name_never_reach_the_storage_path(self):
        self.post(name='a/../../evil.pdf')
        doc = PlanDocument.objects.get()
        self.assertEqual(doc.file_name, 'evil.pdf')
        self.assertNotIn('..', doc.storage_url)
        self.assertEqual(len(self.stored_files()), 1)

    def test_markdown_and_text_keep_their_text(self):
        res = self.post(name='기획안.md', content='# 기획안\n로그인 화면'.encode())
        self.assertEqual(res.json()['type'], 'text/markdown')
        self.assertEqual(PlanDocument.objects.get().text_content, '# 기획안\n로그인 화면')
        self.assertEqual(self.post(name='메모.txt', content=b'\xff\xfe ok').status_code, 201)  # utf-8 이 아니어도 깨지지 않게
        self.assertIn('ok', PlanDocument.objects.filter(file_name='메모.txt').get().text_content)

    def test_long_text_is_trimmed(self):
        with mock.patch('plans.services.TEXT_LIMIT', 5):
            self.post(name='긴글.txt', content='가나다라마바사'.encode())
        self.assertEqual(PlanDocument.objects.get().text_content, '가나다라마')

    def test_images_are_accepted_whatever_the_case(self):
        for name, mime in [('시안.PNG', 'image/png'), ('시안.jpg', 'image/jpeg'), ('시안.Jpeg', 'image/jpeg'), ('시안.gif', 'image/gif'), ('시안.webp', 'image/webp')]:
            self.assertEqual(self.post(name=name, content=b'x').json()['type'], mime, name)

    def test_a_new_upload_replaces_the_current_document(self):
        self.post(name='v1.pdf')
        self.post(name='v2.pdf')
        first, second = PlanDocument.objects.order_by('id')
        self.assertEqual((first.is_current, second.is_current), (False, True))
        self.assertEqual(len(self.stored_files()), 2)  # 이전 파일은 남겨 둬요

    def test_other_projects_current_document_is_left_alone(self):
        other, other_leader = make_project(leader=make_user('l2@example.com'), name='다른 원정대')
        theirs = PlanDocument.objects.create(project=other, uploaded_by=other_leader, source_type='link', link_url='https://example.com/plan')
        self.post()
        theirs.refresh_from_db()
        self.assertTrue(theirs.is_current)

    def test_goes_to_the_current_project(self):
        newer = create_project(self.leader, name='지금 원정대', deadline_at=timezone.now() + timedelta(days=3))
        self.post()
        self.assertEqual(PlanDocument.objects.get().project, newer)

    # ───── 거부 ─────

    def assertRejected(self, res, message):
        self.assertEqual(res.status_code, 400, res.json())
        self.assertIn(message, res.json()['message'])
        self.assertEqual(res.json()['code'], 'invalid')
        self.assertEqual((PlanDocument.objects.count(), self.stored_files()), (0, []))

    def test_unknown_extensions(self):
        self.assertRejected(self.post(name='악성.exe'), '지원하지 않는 파일')
        self.assertRejected(self.post(name='README'), '지원하지 않는 파일')
        self.assertRejected(self.post(name='기획안.pdf.js'), '지원하지 않는 파일')

    def test_empty_file(self):
        self.assertRejected(self.post(content=b''), '빈 파일')

    def test_too_big(self):
        with mock.patch('plans.services.MAX_PLAN_FILE_BYTES', 1024 * 1024):
            self.assertRejected(self.post(content=b'x' * (1024 * 1024 + 1)), '파일이 너무 커요 (최대 1MB)')
            self.assertEqual(self.post(content=b'x' * 1024 * 1024).status_code, 201)  # 딱 한도는 괜찮아요

    def test_missing_file_field(self):
        self.assertRejected(self.post(name=None, memo='파일 없음'), '기획안 파일을 골라 주세요')

    # ───── 누가 ─────

    def test_needs_login(self):
        self.assertEqual(self.post(client=APIClient()).status_code, 401)

    def test_only_the_leader_uploads(self):
        member = add_to(self.project, 'front@example.com', 'front')
        res = self.post(client=api_as(member.user))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'message': '리더만 할 수 있어요', 'code': 'leader_only'})
        self.assertEqual((PlanDocument.objects.count(), self.stored_files()), (0, []))

    # ───── 원정대가 아직 없을 때 ─────

    def test_without_a_project_one_is_made_and_the_user_leads_it(self):
        user = make_user('new@example.com', '새 사용자')
        res = self.post(client=api_as(user))
        self.assertEqual(res.status_code, 201, res.json())
        project = current_project(user)
        self.assertEqual((project.name, is_leader(user, project)), ('내 원정대', True))
        self.assertEqual(PlanDocument.objects.get().project, project)
        self.assertTrue(Checkpoint.objects.filter(project=project, seq=0).exists())
        # 임시 마감: 일주일 뒤 18:00 (한국 시간). 곧 PUT /plan 이 덮어써요
        deadline = timezone.localtime(project.deadline_at)
        self.assertEqual((deadline.hour, deadline.minute), (18, 0))
        self.assertLess(abs(deadline - timezone.localtime() - timedelta(days=7)), timedelta(days=1))

    def test_a_bad_file_creates_no_project(self):
        user = make_user('new@example.com', '새 사용자')
        self.assertRejected(self.post(client=api_as(user), name='악성.exe'), '지원하지 않는 파일')
        self.assertIsNone(current_project(user))
        self.assertFalse(Project.objects.filter(created_by=user).exists())

    # ───── 실패했을 때 ─────

    def test_a_failed_record_leaves_no_stored_file(self):
        with mock.patch('plans.services.set_current_document', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.post()
        self.assertEqual(self.stored_files(), [])
