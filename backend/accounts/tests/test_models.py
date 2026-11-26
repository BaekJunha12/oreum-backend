from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from accounts.models import UserIdentity
from config.testing import ErdContractMixin

User = get_user_model()
DJANGO_USER_COLUMNS = {'last_login', 'is_active', 'is_staff', 'is_superuser'}


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(User, DJANGO_USER_COLUMNS), (UserIdentity, set())]


class UserTests(TestCase):
    def test_email_is_saved_lowercase_and_name_defaults_to_local_part(self):
        user = User.objects.create_user('Junha@Example.COM', 'pw-123456789')
        self.assertEqual(user.email, 'junha@example.com')
        self.assertEqual(user.name, 'Junha')

    def test_user_without_password_cannot_log_in_with_one(self):
        user = User.objects.create_user('google-only@example.com')
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.check_password(''))

    def test_superuser(self):
        admin = User.objects.create_superuser('admin@example.com', 'pw-123456789', name='관리자')
        self.assertTrue(admin.is_staff and admin.is_superuser)

    def test_one_identity_per_provider_account(self):
        a = User.objects.create_user('a@example.com')
        b = User.objects.create_user('b@example.com')
        UserIdentity.objects.create(user=a, provider='google', provider_user_id='sub-1')
        with self.assertRaises(IntegrityError):
            UserIdentity.objects.create(user=b, provider='google', provider_user_id='sub-1')


class AdminTests(TestCase):
    def test_admin_can_create_a_user_with_password(self):
        admin = User.objects.create_superuser('admin@example.com', 'pw-123456789', name='관리자')
        self.client.force_login(admin)
        res = self.client.post('/admin/accounts/user/add/', {
            'email': 'made@example.com', 'name': '관리자가 만듦', 'usable_password': 'true',
            'password1': 'climb-the-oreum-2026', 'password2': 'climb-the-oreum-2026',
        })
        self.assertEqual(res.status_code, 302, res.content[:500])
        self.assertTrue(User.objects.get(email='made@example.com').check_password('climb-the-oreum-2026'))

    def test_admin_pages_open(self):
        admin = User.objects.create_superuser('admin@example.com', 'pw-123456789', name='관리자')
        self.client.force_login(admin)
        self.assertEqual(self.client.get('/admin/accounts/user/').status_code, 200)
        self.assertEqual(self.client.get(f'/admin/accounts/user/{admin.pk}/change/').status_code, 200)
