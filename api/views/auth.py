"""
api/views/auth.py
POST /api/v1/auth/login/         → obtener token
POST /api/v1/auth/logout/        → invalidar token
GET  /api/v1/auth/me/            → perfil del usuario actual
PUT  /api/v1/auth/me/            → actualizar nombre / email
POST /api/v1/auth/change-password/
GET  /api/v1/auth/usuarios/      → lista usuarios (admin)
GET  /api/v1/auth/usuarios/<id>/permisos/  → ver/editar permisos
"""
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers

from api.serializers.ternium import ProfileSerializer
from api.permissions import IsSuperUser


# ─── SERIALIZERS LOCALES ─────────────────────────────────────────────────────
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']


class UserAdminSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.SerializerMethodField()
    permisos = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'nombre_completo',
            'is_active', 'is_staff', 'is_superuser',
            'date_joined', 'last_login', 'permisos',
        ]

    def get_nombre_completo(self, obj):
        return obj.get_full_name() or obj.username

    def get_permisos(self, obj):
        PERMS = [
            'ternium.acceso_remisiones',
            'ternium.acceso_catalogos',
            'ternium.acceso_reportes_kpi',
            'ternium.acceso_trane',
            'ternium.acceso_bancos',
            'ternium.acceso_dashboard',
            'ternium.acceso_diesel',
            'ternium.acceso_dashboard_patio',
            'ternium.acceso_ia',
            'ternium.can_audit_remision',
            'ternium.view_ternium_module',
            'flujo_bancos.acceso_flujo_bancos',
            'api.can_edit_config',
        ]
        return {p.split('.')[1]: obj.has_perm(p) or obj.is_superuser for p in PERMS}


# ─── VISTAS ──────────────────────────────────────────────────────────────────
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password'],
        )
        if not user:
            return Response(
                {'detail': 'Credenciales inválidas.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        if not user.is_active:
            return Response(
                {'detail': 'Usuario desactivado.'},
                status=status.HTTP_403_FORBIDDEN
            )
        token, _ = Token.objects.get_or_create(user=user)
        profile_data = {}
        try:
            profile_data = ProfileSerializer(user.profile).data
        except Exception:
            pass
        return Response({
            'token': token.key,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'nombre_completo': user.get_full_name() or user.username,
                'is_superuser': user.is_superuser,
                'is_staff': user.is_staff,
            },
            'profile': profile_data,
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            request.user.auth_token.delete()
        except Exception:
            pass
        return Response({'detail': 'Sesión cerrada.'}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        profile_data = {}
        try:
            profile_data = ProfileSerializer(user.profile).data
        except Exception:
            pass
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'nombre_completo': user.get_full_name() or user.username,
            'is_superuser': user.is_superuser,
            'is_staff': user.is_staff,
            'profile': profile_data,
        })

    def put(self, request):
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Perfil actualizado.'})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {'old_password': 'Contraseña actual incorrecta.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        # Regenerar token
        Token.objects.filter(user=user).delete()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'detail': 'Contraseña actualizada.', 'token': token.key})


class UsuariosAdminView(APIView):
    permission_classes = [IsAuthenticated, IsSuperUser]

    def get(self, request):
        users = User.objects.select_related('profile').order_by('username')
        serializer = UserAdminSerializer(users, many=True)
        return Response(serializer.data)


class UsuarioPermisosView(APIView):
    permission_classes = [IsAuthenticated, IsSuperUser]

    def get(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'detail': 'Usuario no encontrado.'}, status=404)
        return Response(UserAdminSerializer(user).data)

    def patch(self, request, pk):
        """
        Payload: {"permisos": {"acceso_remisiones": true, "can_audit_remision": false, ...}}
        """
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'detail': 'Usuario no encontrado.'}, status=404)

        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        PERM_MAP = {
            'acceso_remisiones': ('ternium', 'remision'),
            'acceso_catalogos': ('ternium', 'empresa'),
            'acceso_reportes_kpi': ('ternium', 'registrologistico'),
            'acceso_trane': ('ternium', 'controlmanifiestotrane'),
            'acceso_bancos': ('flujo_bancos', 'cuenta'),
            'acceso_dashboard': ('ternium', 'remision'),
            'acceso_diesel': ('cargas_diesel', 'cargadiesel'),
            'acceso_dashboard_patio': ('ternium', 'inventariopatio'),
            'acceso_ia': ('ternium', 'remision'),
            'can_audit_remision': ('ternium', 'remision'),
            'can_edit_config': ('api', 'configuracionsistema'),
        }

        permisos_data = request.data.get('permisos', {})
        for perm_codename, valor in permisos_data.items():
            if perm_codename not in PERM_MAP:
                continue
            app_label, model_name = PERM_MAP[perm_codename]
            try:
                ct = ContentType.objects.get(app_label=app_label, model=model_name)
                perm = Permission.objects.get(content_type=ct, codename=perm_codename)
                if valor:
                    user.user_permissions.add(perm)
                else:
                    user.user_permissions.remove(perm)
            except (Permission.DoesNotExist, ContentType.DoesNotExist):
                pass

        return Response(UserAdminSerializer(user).data)
