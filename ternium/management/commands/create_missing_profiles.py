# ternium/management/commands/create_missing_profiles.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from ternium.models import Profile # <-- ¡Asegúrate que esta ruta sea correcta!

class Command(BaseCommand):
    help = 'Finds users without a profile and creates one for them.'

    def handle(self, *args, **kwargs):
        # Obtenemos todos los usuarios
        users = User.objects.all()
        profiles_created_count = 0

        self.stdout.write("Buscando usuarios sin perfil...")

        for user in users:
            # La forma más simple de verificar si el perfil existe
            # es usando hasattr(). Si 'user.profile' da error, no existe.
            if not hasattr(user, 'profile'):
                Profile.objects.create(user=user)
                profiles_created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Perfil creado para el usuario: {user.username}")
                )

        if profiles_created_count == 0:
            self.stdout.write(self.style.WARNING("Todos los usuarios ya tenían un perfil."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Proceso completado. Se crearon {profiles_created_count} perfiles.")
            )