from facturacion.models import CatalogoSAT

# 1. Claves Prod/Serv (Ejemplo Reciclaje)
CatalogoSAT.objects.get_or_create(tipo='ClaveProdServ', clave='11141600', defaults={'descripcion': 'Desechos no metálicos'})
CatalogoSAT.objects.get_or_create(tipo='ClaveProdServ', clave='01010101', defaults={'descripcion': 'No existe en el catálogo'})

# 2. Claves Unidad
CatalogoSAT.objects.get_or_create(tipo='ClaveUnidad', clave='KGM', defaults={'descripcion': 'Kilogramo'})
CatalogoSAT.objects.get_or_create(tipo='ClaveUnidad', clave='H87', defaults={'descripcion': 'Pieza'})

# 3. Uso CFDI
CatalogoSAT.objects.get_or_create(tipo='UsoCFDI', clave='G03', defaults={'descripcion': 'Gastos en general'})
CatalogoSAT.objects.get_or_create(tipo='UsoCFDI', clave='P01', defaults={'descripcion': 'Por definir'})
CatalogoSAT.objects.get_or_create(tipo='UsoCFDI', clave='S01', defaults={'descripcion': 'Sin efectos fiscales'})

# 4. Formas de Pago
CatalogoSAT.objects.get_or_create(tipo='FormaPago', clave='01', defaults={'descripcion': 'Efectivo'})
CatalogoSAT.objects.get_or_create(tipo='FormaPago', clave='03', defaults={'descripcion': 'Transferencia electrónica de fondos'})
CatalogoSAT.objects.get_or_create(tipo='FormaPago', clave='99', defaults={'descripcion': 'Por definir'})

print("Catálogos básicos cargados correctamente.")