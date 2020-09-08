from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import ugettext_lazy as _


class UserManager(BaseUserManager):
    """
    User model manager where email is the unique identifiers
    for authentication instead of usernames.
    Email addresses will be lowercase.
    """

    @staticmethod
    def _to_lower(email: str) -> str:
        return email.lower()

    def _create_user(self, email: str, password: str, **extra_fields) -> 'User':
        """
        Create user
        """
        if not email:
            raise ValueError(_('The Email must be set'))

        # change to lowercase
        email = self._to_lower(email)

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_user(self, email: str, password: str, **extra_fields) -> 'User':
        """
        Create and save a User with the given email and password.
        """
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields) -> 'User':
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Main User model.
    No username field.
    Emails are stored in lowercase.
    """

    username = None
    balance = models.PositiveIntegerField(default=0)
    email = models.EmailField(
        _('email address'), unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email

