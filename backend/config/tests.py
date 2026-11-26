from django.test import SimpleTestCase, override_settings
from rest_framework import exceptions

from .errors import exception_handler, first_error

FRONT = 'http://localhost:5183'


class HealthAndCorsTests(SimpleTestCase):
    def test_health_needs_no_login(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {'status': 'ok'})

    def test_allowed_origin_gets_cors_headers_with_credentials(self):
        res = self.client.get('/api/health', headers={'Origin': FRONT})
        self.assertEqual(res['Access-Control-Allow-Origin'], FRONT)
        self.assertEqual(res['Access-Control-Allow-Credentials'], 'true')

    def test_preflight_is_answered_without_reaching_the_view(self):
        res = self.client.options('/api/health', headers={
            'Origin': FRONT,
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'authorization, content-type',
        })
        self.assertEqual(res.status_code, 204)
        self.assertIn('PATCH', res['Access-Control-Allow-Methods'])
        self.assertEqual(res['Access-Control-Allow-Headers'], 'authorization, content-type')

    def test_other_origin_gets_no_cors_headers(self):
        res = self.client.get('/api/health', headers={'Origin': 'http://evil.example'})
        self.assertNotIn('Access-Control-Allow-Origin', res)

    @override_settings(CORS_ALLOWED_ORIGINS=['https://oreum.example'])
    def test_origins_come_from_settings(self):
        res = self.client.get('/api/health', headers={'Origin': 'https://oreum.example'})
        self.assertEqual(res['Access-Control-Allow-Origin'], 'https://oreum.example')


class UnknownApiTests(SimpleTestCase):
    def test_unknown_api_path_answers_with_message(self):
        res = self.client.get('/api/plan')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json(), {'message': '아직 없는 API 예요 (GET /api/plan)', 'code': 'no_such_api'})

    def test_trailing_slash_is_not_added(self):
        res = self.client.post('/api/health/', {})
        self.assertEqual(res.status_code, 404)
        self.assertIn('/api/health/', res.json()['message'])


class ErrorShapeTests(SimpleTestCase):
    def test_default_messages_become_short_korean(self):
        res = exception_handler(exceptions.NotAuthenticated(), {})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.data['message'], '로그인이 필요해요')
        self.assertEqual(res.data['code'], 'not_authenticated')

    def test_custom_detail_is_kept(self):
        res = exception_handler(exceptions.PermissionDenied('리더만 할 수 있어요'), {})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data['message'], '리더만 할 수 있어요')

    def test_validation_error_has_first_message_and_all_errors(self):
        res = exception_handler(exceptions.ValidationError({'email': ['형식이 틀렸어요'], 'name': ['비었어요']}), {})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['message'], 'email: 형식이 틀렸어요')
        self.assertEqual(res.data['code'], 'invalid')
        self.assertEqual(set(res.data['errors']), {'email', 'name'})

    def test_first_error_skips_non_field_label(self):
        self.assertEqual(first_error({'non_field_errors': ['둘 다 비었어요']}), '둘 다 비었어요')
        self.assertEqual(first_error({'roles': [{'label': ['비었어요']}]}), 'roles.label: 비었어요')
