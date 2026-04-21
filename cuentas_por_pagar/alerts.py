from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import Factura
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

class AlertSystem:
    def __init__(self):
        self.now = timezone.now()
    
    def enviar_alertas_facturas_por_vencer(self):
        """Envía alertas para facturas que están por vencer (3 días o menos)"""
        facturas_por_vencer = Factura.objects.filter(
            pagada=False,
            dias_restantes_credito__lte=3,
            dias_restantes_credito__gt=0
        ).select_related('orden_compra__proveedor')
        
        for factura in facturas_por_vencer:
            self._enviar_alerta_individual(factura, 'por_vencer')
    
    def enviar_alertas_facturas_vencidas(self):
        """Envía alertas para facturas vencidas"""
        facturas_vencidas = Factura.objects.filter(
            pagada=False,
            dias_restantes_credito__lt=0
        ).select_related('orden_compra__proveedor')
        
        for factura in facturas_vencidas:
            self._enviar_alerta_individual(factura, 'vencida')
    
    def _enviar_alerta_individual(self, factura, tipo_alerta):
        """Envía una alerta individual por email"""
        # Verificar si ya se envió una alerta recientemente (en las últimas 4 horas)
        if (factura.ultima_alerta_enviada and 
            (self.now - factura.ultima_alerta_enviada).total_seconds() < 4 * 3600):
            return
        
        # Obtener usuarios que deben recibir alertas
        usuarios = User.objects.filter(
            is_active=True, 
            email__isnull=False
        ).exclude(email='')
        
        proveedor = factura.orden_compra.proveedor
        
        for usuario in usuarios:
            try:
                if tipo_alerta == 'por_vencer':
                    asunto = f'⚠️ Factura por Vencer: {factura.numero_factura}'
                    mensaje = self._crear_mensaje_por_vencer(factura, usuario)
                else:  # vencida
                    asunto = f'🚨 Factura Vencida: {factura.numero_factura}'
                    mensaje = self._crear_mensaje_vencida(factura, usuario)
                
                send_mail(
                    asunto,
                    mensaje,
                    settings.DEFAULT_FROM_EMAIL,
                    [usuario.email],
                    fail_silently=False,
                )
                
                logger.info(f'Alerta enviada a {usuario.email} para factura {factura.numero_factura}')
                
            except Exception as e:
                logger.error(f'Error enviando alerta a {usuario.email}: {str(e)}')
        
        # Actualizar tracking de alertas
        factura.ultima_alerta_enviada = self.now
        factura.alertas_enviadas += 1
        factura.save()
    
    def _crear_mensaje_por_vencer(self, factura, usuario):
        return f"""
        Hola {usuario.first_name or usuario.username},
        
        La siguiente factura está por vencer:
        
        📋 Factura: {factura.numero_factura}
        🏢 Proveedor: {factura.orden_compra.proveedor.razon_social}
        💰 Monto: ${factura.monto_pendiente:,.2f}
        📅 Fecha Vencimiento: {factura.fecha_vencimiento}
        ⏳ Días Restantes: {factura.dias_restantes_credito}
        🔗 Orden de Compra: {factura.orden_compra.folio}
        
        Por favor, realiza el pago a la brevedad.
        
        Saludos,
        Sistema de Cuentas por Pagar
        """
    
    def _crear_mensaje_vencida(self, factura, usuario):
        return f"""
        URGENTE {usuario.first_name or usuario.username},
        
        La siguiente factura está VENCIDA:
        
        🚨 Factura: {factura.numero_factura}
        🏢 Proveedor: {factura.orden_compra.proveedor.razon_social}
        💰 Monto: ${factura.monto_pendiente:,.2f}
        📅 Fecha Vencimiento: {factura.fecha_vencimiento}
        ⚠️ Días de Retraso: {abs(factura.dias_restantes_credito)}
        🔗 Orden de Compra: {factura.orden_compra.folio}
        
        Se requiere acción inmediata.
        
        Saludos,
        Sistema de Cuentas por Pagar
        """
    
    def ejecutar_todas_alertas(self):
        """Ejecuta todas las alertas (llamar cada 4 horas)"""
        self.enviar_alertas_facturas_por_vencer()
        self.enviar_alertas_facturas_vencidas()
        logger.info("Sistema de alertas ejecutado correctamente")