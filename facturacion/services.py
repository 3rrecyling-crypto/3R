import os
from django.conf import settings
from django.core.files.base import ContentFile
# Libreria satcfdi (instalar con pip install satcfdi)
from satcfdi.create.cfd import cfdi40
from satcfdi.pacs import finkok # Ejemplo usando Finkok

def generar_xml_factura(factura):
    """
    Construye el objeto CFDI 4.0 basado en el modelo Factura
    """
    # 1. Configuración del Emisor
    emisor = cfdi40.Emisor(
        rfc=factura.emisor.rfc,
        nombre=factura.emisor.razon_social,
        regimen_fiscal=factura.emisor.regimen_fiscal.clave
    )

    # 2. Configuración del Receptor
    receptor = cfdi40.Receptor(
        rfc=factura.receptor.rfc,
        nombre=factura.receptor.razon_social,
        uso_cfdi=factura.uso_cfdi.clave,
        domicilio_fiscal_receptor=factura.receptor.codigo_postal,
        regimen_fiscal_receptor=factura.receptor.regimen_fiscal.clave
    )

    # 3. Construcción de Conceptos
    conceptos_cfdi = []
    for c in factura.conceptos.all():
        impuestos_concepto = {
            'Traslados': [cfdi40.Traslado(
                base=c.importe,
                impuesto='002', # IVA
                tipo_factor='Tasa',
                tasa_o_cuota=c.iva_tasa,
                importe=round(float(c.importe) * float(c.iva_tasa), 2)
            )]
        }
        
        # Si hay retención (Reciclaje)
        if c.iva_ret_tasa > 0:
            impuestos_concepto['Retenciones'] = [cfdi40.Retencion(
                base=c.importe,
                impuesto='002',
                tipo_factor='Tasa',
                tasa_o_cuota=c.iva_ret_tasa,
                importe=round(float(c.importe) * float(c.iva_ret_tasa), 2)
            )]

        conceptos_cfdi.append(cfdi40.Concepto(
            clave_prod_serv=c.clave_prod_serv.clave,
            cantidad=c.cantidad,
            clave_unidad=c.clave_unidad.clave,
            unidad=c.clave_unidad.descripcion,
            descripcion=c.descripcion,
            valor_unitario=c.valor_unitario,
            importe=c.importe,
            objeto_imp= '02', # Sí objeto de impuesto
            impuestos=impuestos_concepto
        ))

    # 4. Crear el Comprobante
    invoice = cfdi40.Comprobante(
        serie="A",
        folio=factura.folio,
        fecha=factura.fecha_emision.isoformat(timespec='seconds'),
        forma_pago=factura.forma_pago.clave,
        metodo_pago=factura.metodo_pago.clave,
        moneda=factura.moneda,
        tipo_cambio=1,
        lugar_expedicion=factura.emisor.codigo_postal,
        emisor=emisor,
        receptor=receptor,
        conceptos=conceptos_cfdi,
        subtotal=factura.subtotal,
        total=factura.total,
        exportacion='01', # No aplica
    )
    
    # 5. Sellar (Requiere tus archivos CSD en settings)
    # invoice.sign(key=settings.CSD_KEY, cer=settings.CSD_CER, password=settings.CSD_PASSWORD)
    # return invoice.process()
    
    # NOTA: Como no tienes los archivos reales CSD cargados, esto fallará si lo ejecutas.
    # Debes configurar settings.CSD_KEY apuntando a tu archivo .key real.
    return None 

def timbrar_con_pac(xml_bytes, factura):
    """
    Envía el XML sellado al PAC para obtener el UUID.
    Esto es un SIMULADOR para que funcione tu demo.
    """
    # Aquí iría la conexión real con:
    # pac = finkok.Finkok(user='usuario', password='password')
    # respuesta = pac.stamp(xml_bytes)
    
    # SIMULACIÓN DE ÉXITO:
    import uuid
    factura.uuid = str(uuid.uuid4())
    factura.estatus = 'TIMBRADO'
    
    # Guardamos el XML final
    # factura.xml_file.save(f"{factura.uuid}.xml", ContentFile(xml_bytes))
    factura.save()
    return True