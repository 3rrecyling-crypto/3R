"""
api/pagination.py
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from api.models import ConfiguracionSistema


class DynamicPagePagination(PageNumberPagination):
    """
    Paginación que respeta los valores de ConfiguracionSistema.
    El cliente puede pasar ?page_size=N hasta el máximo configurado.
    """
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200

    def get_page_size(self, request):
        try:
            cfg = ConfiguracionSistema.get_config()
            self.page_size = cfg.items_por_pagina
            self.max_page_size = cfg.items_por_pagina_maximo
        except Exception:
            pass
        return super().get_page_size(request)

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })
