from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.payloads import FALLBACK_ROLE

User = get_user_model()
PASSWORD = 'climb-the-oreum-2026'


def bearer(client, token):
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class LoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('hyeseung@example.com', PASSWORD, name='김혜승')

    def test_login_returns_session_in_front_end_shape(self):
        res = self.client.post('/api/auth/login', {'email': 'hyeseung@example.com', 'password': PASSWORD}, format='json')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(set(body), {'token', 'user'})
        self.assertEqual(body['user'], {'id': str(self.user.pk), 'name': '김혜승', 'email': 'hyeseung@example.com', 'role': FALLBACK_ROLE})
        self.assertEqual(body['token'], Token.objects.get(user=self.user).key)

    def test_email_is_case_insensitive(self):
        res = self.client.post('/api/auth/login', {'email': 'HyeSeung@Example.com', 'password': PASSWORD}, format='json')
        self.assertEqual(res.status_code, 200)

    def test_wrong_password_gives_message(self):
        res = self.client.post('/api/auth/login', {'email': 'hyeseung@example.com', 'password': 'nope'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {'message': '이메일 또는 비밀번호가 틀렸어요', 'code': 'invalid_credentials'})

    def test_missing_field_gives_field_message(self):
        res = self.client.post('/api/auth/login', {'email': 'hyeseung@example.com'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertTrue(res.json()['message'].startswith('password: '))
        self.assertIn('password', res.json()['errors'])

    def test_login_works_while_an_admin_session_cookie_exists(self):
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)  # /admin 에 로그인해 둔 브라우저
        res = csrf_client.post('/api/auth/login', {'email': 'hyeseung@example.com', 'password': PASSWORD}, format='json')
        self.assertEqual(res.status_code, 200)

    def test_same_token_on_second_login(self):
        a = self.client.post('/api/auth/login', {'email': 'hyeseung@example.com', 'password': PASSWORD}, format='json').json()
        b = self.client.post('/api/auth/login', {'email': 'hyeseung@example.com', 'password': PASSWORD}, format='json').json()
        self.assertEqual(a['token'], b['token'])


class TokenTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('back@example.com', PASSWORD, name='백준하')
        self.token = Token.objects.create(user=self.user).key

    def test_me_with_bearer_token(self):
        bearer(self.client, self.token)
        res = self.client.get('/api/auth/me')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['email'], 'back@example.com')

    def test_no_token_is_401_so_front_end_logs_out(self):
        res = self.client.get('/api/auth/me')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res['WWW-Authenticate'], 'Bearer')
        self.assertEqual(res.json()['message'], '로그인이 필요해요')

    def test_wrong_token_is_401(self):
        bearer(self.client, 'not-a-real-token')
        res = self.client.get('/api/auth/me')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()['message'], '로그인이 만료됐어요. 다시 로그인해 주세요')

    def test_drf_token_keyword_is_not_accepted(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)

    def test_logout_deletes_token(self):
        bearer(self.client, self.token)
        res = self.client.post('/api/auth/logout')
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)

    def test_inactive_user_cannot_use_token(self):
        self.user.is_active = False
        self.user.save()
        bearer(self.client, self.token)
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)


class RegisterTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_user_and_logs_in(self):
        res = self.client.post('/api/auth/register', {'email': 'New@Example.com', 'password': PASSWORD, 'name': '새 사람'}, format='json')
        self.assertEqual(res.status_code, 201)
        user = User.objects.get(email='new@example.com')
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(res.json()['user']['id'], str(user.pk))

    def test_duplicate_email(self):
        User.objects.create_user('dup@example.com', PASSWORD)
        res = self.client.post('/api/auth/register', {'email': 'DUP@example.com', 'password': PASSWORD, 'name': '중복'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['message'], 'email: 이미 가입된 이메일이에요')

    def test_weak_password(self):
        res = self.client.post('/api/auth/register', {'email': 'weak@example.com', 'password': '1234', 'name': '약함'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.filter(email='weak@example.com').exists())


class GoogleTests(TestCase):
    def test_google_login_is_not_ready_yet(self):
        res = APIClient().post('/api/auth/google', {}, format='json')
        self.assertEqual(res.status_code, 501)
        self.assertEqual(res.json()['code'], 'not_ready')
        self.assertIn('이메일로 로그인', res.json()['message'])
