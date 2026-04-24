# RH/management/commands/enviar_alertas_rh.py
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta, date
from django.db.models import Q
from django.conf import settings  # <--- IMPORTANTE: Importamos settings para poder usar tu correo
from RH.models import Empleado, Contrato, BajaEmpleado  # <--- IMPORTANTE: RH en mayúsculas

class Command(BaseCommand):
    help = 'Envía alertas automatizadas de Recursos Humanos por correo'

    def add_arguments(self, parser):
        parser.add_argument(
            '--diario',
            action='store_true',
            help='Ejecuta las alertas diarias de contratos de operadores',
        )
        parser.add_argument(
            '--semanal',
            action='store_true',
            help='Ejecuta el resumen semanal para gerencia y RH',
        )

    def handle(self, *args, **options):
        today = date.today()

        if options['diario']:
            self.stdout.write("Ejecutando alertas diarias...")
            self.enviar_alertas_diarias(today)

        if options['semanal']:
            self.stdout.write("Ejecutando resumen semanal...")
            self.enviar_resumen_semanal(today)

    def enviar_alertas_diarias(self, today):
        limite_30_dias = today + timedelta(days=30)

        # Base Query: Contratos determinados de operadores activos que vencen en los próximos 30 días
        contratos_por_vencer = Contrato.objects.filter(
            tipo_contrato='DETERMINADO',
            fecha_fin__range=[today, limite_30_dias],
            empleado__activo=True,
            empleado__eliminado=False,
            empleado__puesto__nombre__icontains='Operador'
        ).select_related('empleado', 'empleado__puesto')

        # 1. Alerta MIGMAR -> Samantha
        contratos_migmar = contratos_por_vencer.filter(empleado__empresa='MIGMAR')
        if contratos_migmar.exists():
            mensaje = "Los siguientes operadores de MIGMAR tienen contrato por vencer en 30 días o menos:\n\n"
            for c in contratos_migmar:
                dias_restantes = (c.fecha_fin - today).days
                mensaje += f"- {c.empleado.nombre_completo} ({c.empleado.numero_empleado or 'S/N'}) | Vence el: {c.fecha_fin} (en {dias_restantes} días)\n"
            
            send_mail(
                subject='🚨 Alerta Diaria: Contratos de Operadores MIGMAR por vencer SISTEMA MIGMAR',
                message=mensaje,
                from_email=settings.EMAIL_HOST_USER,  # Usando correo de entorno
                recipient_list=['samanthagonzalez@transportesmigmar.com'],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS('Correo enviado a Samantha (MIGMAR)'))

        # 2. Alerta MARCO MORALES -> Logística MTY
        contratos_marco = contratos_por_vencer.filter(empleado__empresa='MARCO_MORALES')
        if contratos_marco.exists():
            mensaje = "Los siguientes operadores de MARCO MORALES tienen contrato por vencer en 30 días o menos:\n\n"
            for c in contratos_marco:
                dias_restantes = (c.fecha_fin - today).days
                mensaje += f"- {c.empleado.nombre_completo} ({c.empleado.numero_empleado or 'S/N'}) | Vence el: {c.fecha_fin} (en {dias_restantes} días)\n"
            
            send_mail(
                subject='🚨 Alerta Diaria: Contratos de Operadores MARCO MORALES por vencer SISTEMA MIGMAR',
                message=mensaje,
                from_email=settings.EMAIL_HOST_USER,  # Usando correo de entorno
                recipient_list=['logistica.mty@transportesmigmar.com'],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS('Correo enviado a Logística (MARCO MORALES)'))

    def enviar_resumen_semanal(self, today):
        hace_7_dias = today - timedelta(days=7)

        # Recopilar información de los últimos 7 días
        nuevos_ingresos = Empleado.objects.filter(
            fecha_contratacion__range=[hace_7_dias, today],
            eliminado=False
        )
        
        bajas_recientes = BajaEmpleado.objects.filter(
            fecha_baja__range=[hace_7_dias, today]
        ).select_related('empleado', 'motivo_principal')

        # Construir el mensaje
        mensaje = f"Resumen Semanal de Recursos Humanos SISTEMA MIGMAR({hace_7_dias} al {today}):\n\n"
        
        mensaje += "🟢 NUEVOS INGRESOS (Últimos 7 días):\n"
        if nuevos_ingresos.exists():
            for emp in nuevos_ingresos:
                puesto = emp.puesto.nombre if emp.puesto else 'Sin Puesto'
                empresa = emp.get_empresa_display() if emp.empresa else 'Sin Empresa'
                mensaje += f"- {emp.nombre_completo} | {puesto} | {empresa}\n"
        else:
            mensaje += "- Ningún ingreso registrado en esta semana.\n"

        mensaje += "\n🔴 BAJAS REGISTRADAS (Últimos 7 días):\n"
        if bajas_recientes.exists():
            for baja in bajas_recientes:
                motivo = baja.motivo_principal.nombre if baja.motivo_principal else 'No especificado'
                mensaje += f"- {baja.empleado.nombre_completo} | Baja: {baja.fecha_baja} | Motivo: {motivo}\n"
        else:
            mensaje += "- Ninguna baja registrada en esta semana.\n"

        # KPIs Rápidos Actuales
        total_activos = Empleado.objects.filter(activo=True, eliminado=False).count()
        mensaje += f"\n📊 KPI ACTUAL:\n- Plantilla Total Activa al día de hoy SISTEMA MIGMAR: {total_activos} empleados.\n"

        send_mail(
            subject=f'📊 Resumen Semanal RH: {hace_7_dias.strftime("%d/%m")} - {today.strftime("%d/%m")}',
            message=mensaje,
            from_email=settings.EMAIL_HOST_USER,  # Usando correo de entorno
            recipient_list=['rh@transportesmigmar.com', 'gerenciageneral@transportesmigmar.com'],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS('Resumen semanal enviado a Gerencia y RH'))