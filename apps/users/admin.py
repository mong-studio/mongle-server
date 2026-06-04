from django.contrib import admin

from apps.users.models import RefreshToken, User

admin.site.register(User)
admin.site.register(RefreshToken)
